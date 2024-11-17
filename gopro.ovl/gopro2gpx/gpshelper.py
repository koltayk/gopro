#
# 17/02/2019
# Juan M. Casillas <juanm.casillas@gmail.com>
# https://github.com/juanmcasillas/gopro2gpx.git
#
# Released under GNU GENERAL PUBLIC LICENSE v3. (Use at your own risk)
#

from datetime import datetime
import os
import time


class GPSPoint:

    def __init__(self, latitude = 0.0, longitude = 0.0, elevation = 0.0, time = datetime.fromtimestamp(time.time()), speed = 0.0, temperature = 0.0, dop = 9999):
        self.latitude = latitude
        self.longitude = longitude
        self.elevation = elevation
        self.time = time
        self.speed = speed
        # extensions
        self.hr = 0
        self.cad = 0
        self.cadence = 0
        self.temperature = temperature
        self.dop = dop
        self.atemp = 0
        self.power = 0
        self.distance = 0
        self.left_pedal_smoothness = 0
        self.left_torque_effectiveness = 0


def UTCTime(timedata):
    #
    # time comes: 2014-05-30 20:11:27.200
    # should be formatted to 2014-05-30T20:11:17.200Z
    #

    return timedata.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def CSVTime(timedata):
    #
    # time comes: 2014-05-30 20:11:27.200
    # should be formatted to 2014/05/30 20:11:17.200
    # NEEDS TO BE FIXED, DOESNT PRODUCE SAME TIME AS DASHWARE FROM GPX
    #
    csvtime = timedata.strftime("%Y/%m/%d %H:%M:%S.%f")
    csvtime = csvtime[:-3]
    return csvtime


def generate_GPX(points, start_time = None, trk_name = "exercise"):

    """
    Creates a GPX in 1.1 Format
    """

    if start_time is None:
        start_time = points[0].time

    xml = '<?xml version="1.0" encoding="UTF-8"?>\r\n'
    gpx_attr = [
                'xmlns="http://www.topografix.com/GPX/1/1"' ,
                'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' ,
                'xmlns:wptx1="http://www.garmin.com/xmlschemas/WaypointExtension/v1"' ,
                'xmlns:gpxtrx="http://www.garmin.com/xmlschemas/GpxExtensions/v3"' ,
                'xmlns:gpxtpx="http://www.garmin.com/xmlschemas/TrackPointExtension/v2"' ,
                'xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3"' ,
                'xmlns:trp="http://www.garmin.com/xmlschemas/TripExtensions/v1"' ,
                'xmlns:adv="http://www.garmin.com/xmlschemas/AdventuresExtensions/v1"' ,
                'xmlns:prs="http://www.garmin.com/xmlschemas/PressureExtension/v1"' ,
                'xmlns:tmd="http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1"' ,
                'xmlns:vptm="http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1"' ,
                'xmlns:ctx="http://www.garmin.com/xmlschemas/CreationTimeExtension/v1"' ,
                'xmlns:gpxacc="http://www.garmin.com/xmlschemas/AccelerationExtension/v1"',
        'xmlns:gpxpx="http://www.garmin.com/xmlschemas/PowerExtension/v1"',
        'xmlns:vidx1="http://www.garmin.com/xmlschemas/VideoExtension/v1"',

                'creator="Garmin Desktop App"' ,
                'version="1.1"' ,
                'xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd http://www.garmin.com/xmlschemas/WaypointExtension/v1 http://www8.garmin.com/xmlschemas/WaypointExtensionv1.xsd http://www.garmin.com/xmlschemas/TrackPointExtension/v2 http://www.garmin.com/xmlschemas/TrackPointExtensionv2.xsd http://www.garmin.com/xmlschemas/GpxExtensions/v3 http://www8.garmin.com/xmlschemas/GpxExtensionsv3.xsd http://www.garmin.com/xmlschemas/ActivityExtension/v1 http://www8.garmin.com/xmlschemas/ActivityExtensionv1.xsd http://www.garmin.com/xmlschemas/AdventuresExtensions/v1 http://www8.garmin.com/xmlschemas/AdventuresExtensionv1.xsd http://www.garmin.com/xmlschemas/PressureExtension/v1 http://www.garmin.com/xmlschemas/PressureExtensionv1.xsd http://www.garmin.com/xmlschemas/TripExtensions/v1 http://www.garmin.com/xmlschemas/TripExtensionsv1.xsd http://www.garmin.com/xmlschemas/TripMetaDataExtensions/v1 http://www.garmin.com/xmlschemas/TripMetaDataExtensionsv1.xsd http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensions/v1 http://www.garmin.com/xmlschemas/ViaPointTransportationModeExtensionsv1.xsd http://www.garmin.com/xmlschemas/CreationTimeExtension/v1 http://www.garmin.com/xmlschemas/CreationTimeExtensionsv1.xsd http://www.garmin.com/xmlschemas/AccelerationExtension/v1 http://www.garmin.com/xmlschemas/AccelerationExtensionv1.xsd http://www.garmin.com/xmlschemas/PowerExtension/v1 http://www.garmin.com/xmlschemas/PowerExtensionv1.xsd http://www.garmin.com/xmlschemas/VideoExtension/v1 http://www.garmin.com/xmlschemas/VideoExtensionv1.xsd"'
                ]

  	# BASECAMP:
  	# - doesn't support hr=0
  	# - doesn't support tags:
  	# <gpxtpx:speed>1.0</gpxtpx:speed>
    # <gpxtpx:distance>0</gpxtpx:distance>

    xml += "<gpx " + " ".join(gpx_attr) + ">\r\n"

    xml += "<metadata>\r\n"
    xml += "  <time>%s</time>\r\n" % UTCTime(start_time)
    xml += "</metadata>\r\n"
    xml += "<trk>\r\n"
    xml += "  <name>%s</name>\r\n" % trk_name
    xml += "<trkseg>\r\n"

    #
    # add the points
    #

    #  <trkpt lat="40.327363333" lon="-3.760243333">
    #    <time>2014-06-26T18:40:45Z</time>
    #    <fix>2d</fix>
    #    <sat>7</sat>
    #  </trkpt>

    for p in points:
        pts = f'	<trkpt lat="{p.latitude}" lon="{p.longitude}">\r\n'
        pts += f'		<ele>{p.elevation}</ele>\r\n'
        pts += f'		<time>{UTCTime(p.time)}</time>\r\n'
        pts += f'		<extensions>\r\n'
        pts += f'           <gpxtpx:temp>{p.temperature}</temp>\r\n'
        pts += f'           <gpxtpx:dop>{p.dop}</dop>\r\n'
        pts += f'		    <gpxtpx:TrackPointExtension>\r\n'
        pts += f'		        <gpxtpx:hr>{p.hr}</gpxtpx:hr>\r\n'
        pts += f'		        <gpxtpx:cad>{p.cad}</gpxtpx:cad>\r\n'
        pts += f'		        <gpxtpx:speed>{p.speed}</gpxtpx:speed>\r\n'
        pts += f'		        <gpxtpx:distance>{p.distance}</gpxtpx:distance>\r\n'
        pts += '            </gpxtpx:TrackPointExtension>\r\n'
    	# pts += '        <power>{power}</power>\r\n'
        pts += f'		</extensions>\r\n'
        pts += f'	</trkpt>\r\n'

        xml += pts

    xml += "</trkseg>\r\n"
    xml += "</trk>\r\n"
    xml += "</gpx>\r\n"

    return xml


def generate_KML(gps_points):
    """

    use this for color
    http://www.zonums.com/gmaps/kml_color/

    """

    kml_template = """<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2"> <Document>
    <name>Demo</name>
    <description>Description Demo</description>
    <Style id="yellowLineGreenPoly">
        <LineStyle>
            <color>FF1400BE</color>
            <width>4</width>
            </LineStyle>
        <PolyStyle>
            <color>7f00ff00</color>
        </PolyStyle>
    </Style>
    <Placemark>
        <name>Track Title</name>
        <description>Track Description</description>
        <styleUrl>#yellowLineGreenPoly</styleUrl>
        <LineString>
            <extrude>1</extrude>
            <tessellate>1</tessellate>
            <altitudeMode>absolute</altitudeMode>
            <coordinates>
                %s
            </coordinates>
        </LineString>
    </Placemark>
    </Document>
    </kml>
    """

    lines = []
    for p in gps_points:
        s = "%s,%s,%s" % (p.longitude, p.latitude, p.elevation)
        lines.append(s)

    coords = os.linesep.join(lines)
    kml = kml_template % coords
    return(kml)


def generate_CSV(gps_points):
    csv_template = """DashWare GPX CSV File
Time,Latitude,Longitude,Elevation,AirTemp,HeartRate,Cadence,Power,Roll,Pitch
%s"""

    lines = []
    for p in gps_points:
        s = "%s,%s,%s,%s,%s" % (CSVTime(p.time), p.latitude, p.longitude, p.elevation, ',,,,,')
        lines.append(s)

    coords = os.linesep.join(lines)
    csv = csv_template % coords
    return(csv)
