'''
Created on 2025. febr. 2.
a base_name.ass kiegészítése barometrikus emelkedés/süllyedéssel
@author: kk
'''

import datetime
import glob
import math
import os
import pytz
from tzwhere import tzwhere

from gopro2gpx import gpshelper
from gpmf import goproovl

base_dir_igc = f'/home/kk/gipsy/Koltay Károly'
base_path = '/run/media/kk/CrucialX9/Videos/ovl/2022.10.31 12:52:15_Col_Rodella'
base_name = base_path.split('/')[-1]
video_path = f'{base_path}/{base_name}.MP4'
subtitle_path_new = f'/home/kk/tmp/{base_name}_subtitle.ass'
text_corner_dir = f'{base_path}/tc'


class Args:

    def __init__(self, upovl):
        self.upovl = upovl


def get_gps_point(igc_line, datum_str):
    time_igc = datetime.datetime.strptime(f'{datum_str[:10]} {igc_line[1:7]}', '%Y.%m.%d %H%M%S')
    lat = float(igc_line[7:9]) + float(igc_line[9:14]) / 60000
    lon = float(igc_line[15:18]) + float(igc_line[18:23]) / 60000
    alt_baro = int(igc_line[25:30])
    if alt_baro == 0:
        alt_baro = None
    alt_gps = int(igc_line[30:35])
    gps_point = gpshelper.GPSPoint(lat, lon, alt_gps, time_igc, 0, 0, 0, alt_baro)
    return gps_point


def insert_points(points, point, diff_sec):
    for i in range(diff_sec):
        time_ins = point.time + datetime.timedelta(seconds = i - diff_sec)
        points.append(gpshelper.GPSPoint(point.latitude, point.longitude, point.elevation, time_ins, 0, 0, 0, point.baro_alt))


def before_points(points, diff_sec):
    points_all = list()
    insert_points(points_all, points[0], diff_sec)
    points_all.extend(points)
    return points_all


def get_igc_points(datum_str):
    files = glob.glob(f'{base_dir_igc}/{datum_str[:4]}/koltayk.{datum_str[:4]}-{datum_str[5:7]}-{datum_str[8:10]}.*.IGC')
    igc_points = list()
    if len(files) == 1:
        prev_gps_point = None
        igc_file = files[0]
        goproovl.print_log(f'igc_file: {igc_file}')
        with open(igc_file, "r") as fi:
            for igc_line in fi:
                if igc_line[0] == 'B':
                    gps_point = get_gps_point(igc_line, datum_str)
                    if prev_gps_point:
                        time_diff = int((gps_point.time - prev_gps_point.time).total_seconds())
                        if time_diff > 1:
                            print(f'lyuk az IGC fájlban: {time_diff} s, {gps_point.time}')
                            insert_points(igc_points, gps_point, time_diff - 1)
                    igc_points.append(gps_point)
                    prev_gps_point = gps_point

    return igc_points


def read_igc_points():
    igc_file = '/home/kk/gipsy/Koltay Károly/2020/koltayk.2020-06-12.09-35-37.IGC'
    datum = f'{igc_file.split(".")[-3].replace("-", ".")} '
    igc_file = '/home/kk/Downloads/2025-03-20-XCT-MNE-10.igc'
    datum = f'{igc_file.split("/")[-1].split(".")[-2].replace("-", ".")} '
    # datum = f'{igc_file.split(".")}'
    out_file = f'{igc_file}.txt'
    with open(out_file, "w") as fo:
        with open(igc_file, "r") as fi:
            for igc_line in fi:
                if igc_line[0] == 'B':
                    gps_point = get_gps_point(igc_line, datum)
                    string = f'{gps_point.time} {gps_point.elevation} {gps_point.baro_alt}'
                    print(string, file = fo, flush = True)


def create_subtitles(datum_str):
    igc_points = get_igc_points(datum_str)
    if igc_points:
        datetime_of_file = datetime.datetime.strptime(datum_str[:19], '%Y.%m.%d %H:%M:%S')
        os.makedirs(text_corner_dir, exist_ok = True)
        timezone_str = tzwhere.tzwhere().tzNameAt(igc_points[0].latitude, igc_points[0].longitude)
        if timezone_str:
            timezone = pytz.timezone(timezone_str)
            if timezone:
                start_time_igc = igc_points[0].time
                local_time_igc = timezone.fromutc(start_time_igc)
        subtitle_igc_diff_sec = int((datetime_of_file - local_time_igc.replace(tzinfo = None)).total_seconds())
        metadata, goproovl.duration_sec = goproovl.get_metadata(video_path)
        goproovl.ovl_size = (200, 90)
        goproovl.text_corner_dir = text_corner_dir
        goproovl.timezone = timezone
        goproovl.args = Args(True)
        goproovl.lon_factor = math.cos(math.radians(igc_points[0].latitude))
        # goproovl.get_corner(video_path, 0, 0)
        if subtitle_igc_diff_sec > 0:
            points_needed = igc_points[subtitle_igc_diff_sec:]
        elif subtitle_igc_diff_sec < 0:
            points_needed = before_points(igc_points, -subtitle_igc_diff_sec)
        goproovl.subtitle_file = subtitle_path_new
        goproovl.gps_from_igc = True
        gps_points, true_gps_points = goproovl.create_subtitles(points_needed, datetime_of_file)


if __name__ == '__main__':
    read_igc_points()
    # create_subtitles(datum_str)
    print("kész")
