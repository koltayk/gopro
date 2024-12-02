#!/usr/bin/env python
#
# 17/02/2019
# Juan M. Casillas <juanm.casillas@gmail.com>
# https://github.com/juanmcasillas/gopro2gpx.git
#
# Released under GNU GENERAL PUBLIC LICENSE v3. (Use at your own risk)
#

import datetime
import sys

from gpmf import goproovl

from . import fourCC
from . import gpmf
from . import gpshelper


def BuildGPSPoints(data, skip = True, skipDop = True, dopLimit = 500):
    """
    Data comes UNSCALED so we have to do: Data / Scale.
    Do a finite state machine to process the labels.
    GET
     - SCAL     Scale value
     - GPSF     GPS Fix
     - GPSU     GPS Time
     - GPS5     GPS Data
     - GPSP     GPS Precision
    """

    points = []
    start_time = None
    SCAL = fourCC.XYZData(1.0, 1.0, 1.0)
    GPSU = None
    TMPC = None
    SYST = fourCC.SYSTData(0, 0)

    stats = {
        'ok': 0,
        'badfix': 0,
        'badfixskip': 0,
        'empty': 0,
        'baddop': 0,
        'baddopskip': 0,
        'badspeep': 0
    }

    # GPSP is 100x DoP
    # https://en.wikipedia.org/wiki/Dilution_of_precision_(navigation)
    # Default value is 9999 (no lock). GoPro say that under 500 is good.
    # Wikipedia indicates:
    #   Ideal: <100
    #   Excellent: 100-200
    #   Good: 200-500
    #   Moderate: 500-1000
    #   Fair: 1000-2000
    #   Poor: >2000

    GPSP = None  # no lock
    GPSFIX = 0  # no lock.
    TSMP = 0
    DVNM = "Unknown"
    for d in data:
        if d.fourCC == 'SCAL':
            SCAL = d.data
        elif d.fourCC == "DVNM":
            DVNM = d.data
        elif d.fourCC == "TMPC":
            TMPC = d.data
        elif d.fourCC == 'GPSU':
            GPSU = d.data
            goproovl.print_log(f"GPSU {d.data}")
            if start_time is None:
                start_time = GPSU
        elif d.fourCC == 'GPSF':
            if d.data != GPSFIX:
                goproovl.print_log("GPSFIX change to %s [%s]" % (d.data, fourCC.LabelGPSF.xlate[d.data]))
            GPSFIX = d.data

        elif d.fourCC == 'TSMP':
            if TSMP == 0:
                TSMP = d.data
            else:
                TSMP = d.data - TSMP

        elif d.fourCC == 'GPS5':
            # we have to use the REPEAT value.
            # gopro has a 18 Hz sample of writting the GPS5 value, so use it to compute delta
            # goproovl.print_log("len", len(d.data))
            t_delta = 1 / len(d.data)
            sample_count = 0
            for item in d.data:

                if item.lon == item.lat == item.alt == 0:
                    goproovl.print_log("Warning: Skipping empty point")
                    stats['empty'] += 1
                    continue

                if GPSFIX < 3:
                    stats['badfix'] += 1
                    if skip:
                        goproovl.print_log("Warning: Skipping point due GPSFIX<3")
                        stats['badfixskip'] += 1
                        continue

                if GPSP is not None and GPSP > dopLimit:
                    stats["baddop"] += 1
                    if skipDop:
                        goproovl.print_log("Warning: skipping point due to GPSP>limit. GPSP: %s, limit: %s" % (GPSP, dopLimit))
                        stats["baddopskip"] += 1
                        continue

                retdata = [ float(x) / float(y) for x, y in zip(item._asdict().values() , list(SCAL)) ]

                gpsdata = fourCC.GPSData._make(retdata)
                if gpsdata.speed > 35:
                    stats["badspeep"] += 1
                    goproovl.print_log(f"Warning: Skipping point due to speed {gpsdata.speed} > 35 m/s")
                    continue

                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, GPSU + datetime.timedelta(seconds = sample_count * t_delta), gpsdata.speed, TMPC, GPSP)
                if points and p.time < points[-1].time:
                    goproovl.print_log(f"Warning: p.time < points[-1].time {p.time} < {points[-1].time}  len(points): {len(points)}")
                else:
                    points.append(p)
                stats['ok'] += 1
                sample_count += 1

        elif d.fourCC == 'SYST':
            data = [ float(x) / float(y) for x, y in zip(d.data._asdict().values() , list(SCAL)) ]
            if data[0] != 0 and data[1] != 0:
                SYST = fourCC.SYSTData._make(data)

        elif d.fourCC == 'GPRI':
            # KARMA GPRI info

            if d.data.lon == d.data.lat == d.data.alt == 0:
                goproovl.print_log("Warning: Skipping empty point")
                stats['empty'] += 1
                continue

            if GPSFIX == 0:
                stats['badfix'] += 1
                if skip:
                    goproovl.print_log("Warning: Skipping point due GPSFIX==0")
                    stats['badfixskip'] += 1
                    continue

            data = [ float(x) / float(y) for x, y in zip(d.data._asdict().values() , list(SCAL)) ]
            gpsdata = fourCC.KARMAGPSData._make(data)

            if SYST.seconds != 0 and SYST.miliseconds != 0:
                goproovl.print_log("XX", SYST.miliseconds)
                p = gpshelper.GPSPoint(gpsdata.lat, gpsdata.lon, gpsdata.alt, datetime.fromtimestamp(SYST.miliseconds), gpsdata.speed)
                points.append(p)
                stats['ok'] += 1

        elif d.fourCC == 'GPSP':
            if GPSP != d.data:
                goproovl.print_log("GPSP change to %s [%s]" % (d.data, fourCC.LabelGPSP.xlate(d.data)))
            GPSP = d.data

    goproovl.print_log("-- stats -----------------")
    total_points = 0
    for i in stats.keys():
        total_points += stats[i]
    goproovl.print_log("Device: %s" % DVNM)
    goproovl.print_log("- Ok:              %5d" % stats['ok'])
    goproovl.print_log("- GPSFIX=0 (bad):  %5d (skipped: %d)" % (stats['badfix'], stats['badfixskip']))
    goproovl.print_log("- GPSP>%4d (bad): %5d (skipped: %d)" % (dopLimit, stats['baddop'], stats['baddopskip']))
    goproovl.print_log("- Empty (No data): %5d" % stats['empty'])
    goproovl.print_log("Total points:      %5d" % total_points)
    goproovl.print_log("--------------------------")
    return(points, start_time, DVNM)


def main_core(gopro_binary, input_file, out_file_base, lfd):
    points = []
    start_time = None
    goproovl.lfd = lfd

    data = gpmf.parseStream(gopro_binary, 0)

    with open(f"{out_file_base}/gpmf.klv", "w") as fd:
        for row in data:
            fd.write(str(row) + "\n")

    points, start_time, device_name = BuildGPSPoints(data)

    if len(points) == 0:
        goproovl.print_log(f"Can't create file. No GPS info in {input_file}. Exitting")
        sys.exit(0)

    kml = gpshelper.generate_KML(points)
    with open(f"{out_file_base}/gpmf.kml", "w") as fd:
        fd.write(kml)

    # csv = gpshelper.generate_CSV(points)
    # with open("%s.csv" % config.outputfile , "w+") as fd:
    #    fd.write(csv)
    #
    # gpx = gpshelper.generate_GPX(points, start_time, trk_name = device_name)
    # with open(f"{out_file_base}/gpmf.gpx", "w") as fd:
    #     fd.write(gpx)

    return points, start_time


def main():
    main_core()


if __name__ == "__main__":
    main()
