#!/usr/bin/env python3

"""
Overlay the videos in dir (input directory) with GPS data (time, high, speed, direction, vertical speed) and concatenate the overlayed videos.
Based on https://github.com/krisp/gopro2gpx/blob/master/gopro2gpx.py
Output GPS track from GoPro videos in Garmin GPX format.

Accepts an arbitrary number of input videos in dir (input directory), an outputname as the base name of the created video
The GPS points from multiple videos are concatenated into a single gpx output file.

Adjust the FFMPEG global below if ffmpeg is in a non-standard location. This
should work on Windows as well with proper path to ffmpeg.
"""

import argparse
import datetime
import json
import math
import os
from pathlib import Path
import re
import shutil
from subprocess import Popen, PIPE

from PIL import Image, ImageDraw, ImageFont  # @UnresolvedImport only for PyDev
import pytz
from tzwhere import tzwhere  # https://github.com/pegler/pytzwhere/issues/53

from gopro2gpx import gopro2gpx
import numpy as np

FFMPEG = "/usr/bin/ffmpeg"
FFPROBE = "/usr/bin/ffprobe"
GPSFREQU = 18
MP4 = 'MP4'
PNG = '.png'
MAXEND = 1000
SUBTITLES_PREF = """[Script Info]
Title: Example Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None

[V4 Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: White1t, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,1,1
Style: White2t, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,6,1
Style: White3t, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,11,1
Style: Black1t, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,1,1
Style: Black2t, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,6,1
Style: Black3t, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,5,1,1,11,1
Style: White1b, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,1,1
Style: White2b, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,6,1
Style: White3b, Arial,5, &H00FFFFFF, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,11,1
Style: Black1b, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,1,1
Style: Black2b, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,6,1
Style: Black3b, Arial,5, &H00000000, &H000000FF, &H00000000, &H80000000,-1,0,0,0,100,100,0,0,0,0,0,1,1,1,11,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""


def time_in_sec(min_sec):
    duration = str(min_sec).split(":")
    seconds = float(duration[-1])
    if len(duration) > 1:
        seconds += 60 * int(duration[-2])
    return seconds


def dump_metadata():
    global duration_sec
    global ovl_pos_y
    params = [FFPROBE, '-i', concat_file, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-hide_banner']
    (o, e) = Popen(params, stdout = PIPE, stderr = PIPE).communicate()
    metadata = json.loads(o)
    duration_sec = float(metadata['format']['duration'])
    print(f"Length of file is: {duration_sec} sec")
    if args.upovl:
        ovl_pos_y = 0
        if args.rotate:
            img_pos_x = metadata['streams'][0]['width'] - ovl_size[0]
            img_pos_y = metadata['streams'][0]['height'] - ovl_size[1]
        else:
            img_pos_x = 0
            img_pos_y = 0
    else:
        ovl_pos_y = metadata['streams'][0]['height'] - ovl_size[1]
        if args.rotate:
            img_pos_x = metadata['streams'][0]['width'] - ovl_size[0]
            img_pos_y = 0
        else:
            img_pos_x = 0
            img_pos_y = metadata['streams'][0]['height'] - ovl_size[1]

    params = [FFMPEG, '-threads', '16', '-i', concat_file, '-vf', f'fps=1,crop={ovl_size[0]}:{ovl_size[1]}:{img_pos_x}:{img_pos_y}', text_corner_dir + '/%04d.bmp', '-hide_banner']
    rc = call_prog(params)
    print_log(f"Read frames pro second from {concat_file} to {text_corner_dir} returncode: {rc}")
    if rc != 0:
        exit()

    params = [FFMPEG, '-threads', '16', '-y', '-i', concat_file, '-codec', 'copy', '-map', '0:2', '-f', 'rawvideo', '-']
    print_log(" ".join(params))
    (o, e) = Popen(params, stdout = PIPE, stderr = PIPE).communicate()
    Path(gpmf_file).write_bytes(o)
    print_log(f"Read gpmf data from {concat_file}")
    return o
    # return BytesIO(o)


def print_time(total_seconds, text):
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print_log(f"{text} duration: {total_seconds:2.2f} sec:   {hours:.0f} h {minutes:.0f} m {seconds:2.2f} s")


def calc_vertical_speed(step, alt0, alt1):
    return (alt1 - alt0) / step


def calc_direction_ift(gps_datum_prev, gps_datum_next, text0, text1):
    direction = angle_from_coordinate(gps_datum_prev.latitude, gps_datum_prev.longitude, gps_datum_next.latitude, gps_datum_next.longitude)
    diff_sec = (gps_datum_next.time - gps_datum_prev.time).total_seconds()
    vertical_speed = calc_vertical_speed(diff_sec, gps_datum_prev.elevation, gps_datum_next.elevation)
    text0 += f'   {direction:.0f} °'
    text1 += f'   {vertical_speed:.1f} m/s'
    return text0, text1


def create_subtitle_text(gps_points, start_time, act_sec, sfd):
    gps_datum_prev = None if act_sec == 0 else gps_points[act_sec - 1]
    gps_datum = gps_points[act_sec]
    gps_datum_next = None if act_sec + 1 == len(gps_points) else gps_points[act_sec + 1]
    time = start_time + datetime.timedelta(seconds = act_sec)
    if gps_datum and gps_datum.latitude:
        speed = 3.6 * gps_datum.speed
        heigh = gps_datum.elevation
        text0 = f'{speed:.0f} km/h'
        text1 = f'{heigh:.0f} m'
        if gps_datum_prev and gps_datum_prev.latitude and gps_datum_next and gps_datum_next.latitude:
            text0, text1 = calc_direction_ift(gps_datum_prev, gps_datum_next, text0, text1)
        elif gps_datum_prev and gps_datum_prev.latitude:
            text0, text1 = calc_direction_ift(gps_datum_prev, gps_datum, text0, text1)
        elif gps_datum_next and gps_datum_next.latitude:
            text0, text1 = calc_direction_ift(gps_datum, gps_datum_next, text0, text1)
    else:
        text0 = ''
        text1 = ''
    if timezone:
        time_str = timezone.fromutc(time).strftime("%Y.%m.%d %H:%M:%S")
    else:
        time_str = time.strftime("%Y.%m.%d %H:%M:%S")
    colorText = get_text_color(act_sec)
    ts0 = datetime.timedelta(seconds = act_sec)
    ts1 = datetime.timedelta(seconds = act_sec + 1)
    if args.upovl:
        line_nr = '1t'
        print(f'Dialogue: 0,{ts0}.00,{ts1}.00.00,{colorText}{line_nr},,0000,0000,0000,,{time_str}', file = sfd)
        if text0:
            line_nr = '2t'
            print(f'Dialogue: 0,{ts0}.00,{ts1}.00,{colorText}{line_nr},,0000,0000,0000,,{text0}', file = sfd)
            line_nr = '3t'
            print(f'Dialogue: 0,{ts0}.00,{ts1}.00,{colorText}{line_nr},,0000,0000,0000,,{text1}', file = sfd)
    else:
        line_nr = '3b'
        print(f'Dialogue: 0,{ts0}.00,{ts1}.00,{colorText}{line_nr},,0000,0000,0000,,{time_str}', file = sfd)
        if text0:
            line_nr = '1t'
            print(f'Dialogue: 0,{ts0}.00,{ts1}.00,{colorText}{line_nr},,0000,0000,0000,,{text0}', file = sfd)
            line_nr = '2t'
            print(f'Dialogue: 0,{ts0}.00,{ts1}.00,{colorText}{line_nr},,0000,0000,0000,,{text1}', file = sfd)


def angle_from_coordinate(lat1, long1, lat2, long2):
    dLon = (long2 - long1)

    y = math.sin(dLon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)

    brng = math.atan2(y, x)

    brng = math.degrees(brng)
    brng = (brng + 360) % 360
    brng = 360 - brng  # count degrees clockwise - remove to make counter-clockwise

    return brng


def rotate(file_name):
    if args.rotate:
        file_name_rotate = file_name.replace(MP4, 'rotate.' + MP4)
        params = [FFMPEG, '-threads', '16', '-i', file_name, '-map_metadata', '0', '-metadata:s:v:0', 'rotate=0', '-c', 'copy', '-y', file_name_rotate, '-hide_banner']
        rc = call_prog(params)

        print_log(f"Rotating output {file_name} to {file_name_rotate} returncode: {rc}")
        if rc != 0:
            exit()

        return file_name_rotate
    else:
        return file_name


def call_prog(params):
    print_log(" ".join(params))
    process = Popen(params, stdout = PIPE, stderr = PIPE, encoding = 'utf8')
    while True:
        output = process.stderr.readline()
        if len(output) == 0 and process.poll() is not None:
            break
        if output:
            print_log(output.strip())
    rc = process.poll()
    return rc


def add_subtitles(points, start_time):
    p_index = 0
    gps_points = []
    curr_time_rounded = start_time
    for act_sec in range(round(duration_sec)):
        p_index, dist_sec_last = get_nearest_gps_datum(points, p_index, curr_time_rounded)
        point = points[p_index]
        if dist_sec_last > 0.5:
            point = None
        gps_points.append(point)
        print(f"{act_sec} {curr_time_rounded} {p_index} {points[p_index].time}")
        curr_time_rounded = curr_time_rounded + datetime.timedelta(seconds = 1)
    subtitle_file = f'{out_file_base}/subtitle.ass'
    with open(subtitle_file, "w") as sfd:
        print(SUBTITLES_PREF, file = sfd)
        for act_sec in range(len(gps_points)):
            create_subtitle_text(gps_points, start_time, act_sec, sfd)

    out_video_part = f'{out_file_base}/{base_name}.{MP4}'
    params = [FFMPEG, '-threads', '16', '-y', '-i', concat_file, '-vf', f'ass={subtitle_file}', '-preset', 'veryfast', out_video_part, '-hide_banner']
    rc = call_prog(params)
    print_log(f"Writing subtitles to {out_video_part} returncode: {rc}")
    if rc != 0:
        exit()


def get_nearest_gps_datum(points, p_index, curr_time_rounded):
    dist_sec_last = abs((points[p_index].time - curr_time_rounded).total_seconds())
    dist_sec_curr = dist_sec_last
    while dist_sec_curr <= dist_sec_last:
        p_index += 1
        dist_sec_last = dist_sec_curr
        dist_sec_curr = abs((points[p_index].time - curr_time_rounded).total_seconds())

    return p_index - 1, dist_sec_last


def print_log(param):
    string = str(datetime.datetime.now()) + " " + param.replace("\n", "")
    print(string)
    print(string, file = lfd, flush = True)


def concat_video(video_parts, concat_file_result):
    video_file_list = out_file_base_tmp + "/files"
    with open(video_file_list, "w") as fd:
        # for file, dur in video_parts:
        for file in video_parts:
            print(f"file '{file}'", file = fd)
            # print(f"duration {dur}", file = fd)
    print_log(f"Writing video parts list to {video_file_list}")
    params = [FFMPEG, '-threads', '16', '-y', '-safe', '0', '-f', 'concat', '-segment_time_metadata', '1', '-i', video_file_list, '-vf', 'select=concatdec_select', '-af', 'aselect=concatdec_select,aresample=async=1', '-map', '0', concat_file_result, '-hide_banner']
    rc = call_prog(params)
    print_log(f"Concatenated to {concat_file_result} returncode: {rc}")
    if rc != 0:
        exit()
    return concat_file_result


def get_text_color (act_sec):
    image_file = f"{text_corner_dir}/{(act_sec+1):04d}.bmp"
    img = Image.open(image_file)

    img_size = img.size
    # print(img_size)

    text_corner = np.asarray(img)[0:img_size[0], 0:img_size[1]]
    # ld_img= Image.fromarray(text_corner)
    # ld_img.show()

    rgb_result = np.array([0., 0., 0.])
    for line in text_corner:
        rgb_line = np.array([0., 0., 0.])
        for rgb in line:
            rgb_px = np.array(rgb)
            rgb_line += rgb_px
        rgb_result += rgb_line / line.shape[0]

    rgb_result = rgb_result / text_corner.shape[0]
    brightness0 = rgb_result[0] * 0.299 + rgb_result[1] * 0.587 + rgb_result[2] * 0.114
    brightness = inv_gam_sRGB(rgb_result[0]) * 0.2126 + inv_gam_sRGB(rgb_result[1]) * 0.7152 + inv_gam_sRGB(rgb_result[2]) * 0.0722
    # brightness = math.sqrt(.299 * rgb_result[0] * rgb_result[0] + .587 * rgb_result[1] * rgb_result[1] + .114 * rgb_result[2] * rgb_result[2])
    print_log(f"act_sec {act_sec} RGB {rgb_result} brightness {brightness} brightness0 {brightness0}")
    if brightness < 0.22:
        return 'White'
    else:
        return 'Black'


def inv_gam_sRGB(color):
    colorChannel = color / 255
    if colorChannel <= 0.04045:
            return colorChannel / 12.92
    else:
            return math.pow(((colorChannel + 0.055) / 1.055), 2.4)


def cut(begin, end, index, video_file_name):
    video_file_name_rot = rotate(video_file_name)
    out_video_part = f'{tmp_video_dir_inp}/part-{str(index)}.'
    out_video_part_ts = f'{out_video_part}ts'
    beg = str(begin)
    if end == 0:
        end = MAXEND
    dur = str(end - begin)
    params = [FFMPEG, '-threads', '16', '-y', '-ss', beg, '-t', dur, '-i', video_file_name_rot, '-map', '0:0', '-map', '0:1', '-map', '0:3', '-c', 'copy', '-copyts', out_video_part_ts, '-hide_banner']
    rc = call_prog(params)
    print_log(f"Writing {out_video_part_ts} returncode: {rc}")
    if rc != 0:
        exit()
    return out_video_part_ts


def parseArgs():
    parser = argparse.ArgumentParser()
    parser.add_argument("-b", "--begin", help = "begin time in first video, mm:ss", default = 0)
    parser.add_argument("-e", "--end", help = "end time in last video, mm:ss", default = 0)
    parser.add_argument("-r", "--rotate", help = "rotate 180°, boolean", default = False)
    parser.add_argument("-u", "--upovl", help = "overlay left up°, boolean", default = True)
    # parser.add_argument("-o", "--outdir", help = "output directory", default = '/home/kk/Videos/')
    parser.add_argument("-o", "--outdir", help = "output directory", default = '/run/media/kk/CrucialX9/Videos/')
    parser.add_argument("dir", help = "input directory")
    parser.add_argument("outputname", help = "output name")
    args = parser.parse_args()

    return args


if __name__ == "__main__":
    args = parseArgs()
    timezone = None
    out_file_base_tmp = None
    base_name = None
    begin = 0
    end = 0
    duration_sec = 0
    ovl_pos_y = 0
    # ovl_pos_y = 2060
    # ovl_pos_y = 1430
    ovl_size = (200, 90)
    start = datetime.datetime.now()
    out_file_base = f'{args.outdir}pgovl/{args.dir.split("/")[-1]}/{args.outputname}'
    log_file = out_file_base + "/log"
    out_file_base_tmp = out_file_base + "/tmp"
    tmp_video_dir_inp = out_file_base_tmp + '/inp'
    os.makedirs(tmp_video_dir_inp, exist_ok = True)
    text_corner_dir = tmp_video_dir_inp + '/tc'
    img_dir = tmp_video_dir_inp + '/images'
    concat_file = f'{tmp_video_dir_inp}/concat.mp4'
    gpmf_file = f'{out_file_base}/gpmf.bin'
    with open(log_file, "w+") as lfd:
        print_log(f"begin {args.begin}, end {args.end}")
        inp_video_files_all = sorted(Path(args.dir).iterdir())
        inp_video_files = None
        video_parts_inp = list()
        if os.path.exists(out_file_base):
            shutil.rmtree(out_file_base_tmp)
        os.makedirs(text_corner_dir, exist_ok = True)
        os.makedirs(img_dir, exist_ok = True)
        # create one list of all points in all of the videos on cmd line
        points = list()
        file_list = list()
        p = re.compile(args.dir + '/(.*)' + "\." + MP4 + '$')
        # p = re.compile(args.dir + '/(GH.*)' + "\." + MP4 + '$')
        if not inp_video_files:
            inp_video_files = inp_video_files_all
        for file in inp_video_files:
            print_log(f"inp_video_file {file}")
            video_file_name = str(file)
            m = p.match(video_file_name)
            if  m:
                file_list.append(m.group(1))

        for index, video_name in enumerate(file_list):
            video_file_name = f'{args.dir}/{video_name}.{MP4}'
            if index == 0:
                begin = time_in_sec(args.begin)
            else:
                begin = 0
            if index + 1 == len(file_list) and args.end:
                end = time_in_sec(args.end)
            else:
                end = 0
            video_parts_inp.append(cut(begin, end, index, video_file_name))

        concat_video(video_parts_inp, concat_file)

        points, start_time = gopro2gpx.main_core(dump_metadata(), concat_file, out_file_base)
        if points:
            for point in points:
                if point.dop < 500:
                    break
            if point.latitude and point.longitude:
                timezone_str = tzwhere.tzwhere().tzNameAt(point.latitude, point.longitude)
                if timezone_str:
                    timezone = pytz.timezone(timezone_str)
            if timezone:
                local_time = timezone.fromutc(start_time)
            start_time_local = datetime.datetime.fromtimestamp(round(local_time.timestamp()))
            start_time_rounded = datetime.datetime.fromtimestamp(round(start_time.timestamp()))
            base_name = f'{start_time_local}_{args.outputname}'
            add_subtitles(points, start_time_rounded)
            new_dir = f'{args.outdir}ovl/{base_name}'
            shutil.rmtree(f'{new_dir}', ignore_errors = True)
            shutil.move(out_file_base, new_dir)
            shutil.rmtree(f'{new_dir}/tmp')

        dur = datetime.datetime.now()
        process_duration = (dur - start).total_seconds()
        print_time(process_duration, "process")
