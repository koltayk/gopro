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
from io import BytesIO
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
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


def time_in_sec(min_sec):
    duration = str(min_sec).split(":")
    seconds = float(duration[-1])
    if len(duration) > 1:
        seconds += 60 * int(duration[-2])
    return seconds


def dump_metadata():
    global duration_sec
    # proc = Popen([FFPROBE, concat_file, '-hide_banner'], stdout = PIPE, stderr = PIPE, encoding = 'utf8')
    # global ovl_pos_y
    # for line in list(proc.stderr):
    #     print_log(line)
    #     m = re.match(".*Duration: ([^,]+),.*", line)
    #     if m:
    #         duration_sec = time_in_sec(m.group(1))
    #     m = re.match(".*Stream #0:0.*, \d+x(\d+) .*", line)
    #     if m:
    #         if args.upovl:
    #             ovl_pos_y = 0
    #         else:
    #             ovl_pos_y = int(m.group(1)) - ovl_size[1]
    # print_time(duration_sec, "temp_dir")

    params = [FFPROBE, '-i', concat_file, '-v', 'quiet', '-print_format', 'json', '-show_format', '-show_streams', '-hide_banner']
    (o, e) = Popen(params, stdout = PIPE, stderr = PIPE).communicate()
    metadata = json.loads(o)
    duration_sec = float(metadata['format']['duration'])
    print(f"Length of file is: {duration_sec} sec")
    if args.upovl:
        ovl_pos_y = 0
    else:
        ovl_pos_y = metadata['streams'][0]['width'] - ovl_size[1]

    params = [FFMPEG, '-i', concat_file, '-vf', 'fps=1', text_corner_dir + '/%04d.bmp']
    rc = call_prog(params)
    print_log(f"Read frames pro second from {concat_file} to {text_corner_dir} returncode: {rc}")
    if rc != 0:
        exit()

    (o, e) = Popen([FFMPEG, '-y', '-i', concat_file, '-codec', 'copy', '-map', '0:2', '-f', 'rawvideo', '-'], stdout = PIPE, stderr = PIPE).communicate()
    Path(gpmf_file).write_bytes(o)

    return o
    # return BytesIO(o)


def print_time(total_seconds, text):
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print_log(f"{text} duration: {total_seconds:2.2f} sec:   {hours:.0f} h {minutes:.0f} m {seconds:2.2f} s")


def calc_vertical_speed(step, alt0, alt1):
    return (alt1 - alt0) / step


def getDst(gps_time):
    time = timezone.fromutc(gps_time)
    return time.strftime("%Y.%m.%d %H:%M:%S")


def calc_direction_ift(gps_datum_prev, gps_datum_next, text0, text1):
    direction = angle_from_coordinate(gps_datum_prev.latitude, gps_datum_prev.longitude, gps_datum_next.latitude, gps_datum_next.longitude)
    diff_sec = (gps_datum_next.time - gps_datum_prev.time).total_seconds()
    vertical_speed = calc_vertical_speed(diff_sec, gps_datum_prev.elevation, gps_datum_next.elevation)
    text0 += f'   {direction:.0f} °'
    text1 += f'   {vertical_speed:.1f} m/s'
    return text0, text1


def create_ovl_img(gps_points, start_time, act_sec):
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
    make_img(time, act_sec, text0, text1)


def create_pre_imgs(first_gps_fix_time, gps_diff):
    for i in range(int(round(gps_diff - begin))):
        time = first_gps_fix_time - datetime.timedelta(seconds = i + 1)
        make_img(time, i, '', '')


def angle_from_coordinate(lat1, long1, lat2, long2):
    dLon = (long2 - long1)

    y = math.sin(dLon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(dLon)

    brng = math.atan2(y, x)

    brng = math.degrees(brng)
    brng = (brng + 360) % 360
    brng = 360 - brng  # count degrees clockwise - remove to make counter-clockwise

    return brng


def create_list_images(chunk):
    params = list()
    for img in chunk:
        params.append('-i')
        params.append(str(img))
    return params


def chunker(seq, size):
    return list(seq[i:i + size] for i in range(0, len(seq), size))


def rotate(file_name):
    if args.rotate:
        # ffmpeg -i '/home/kk/Videos/tmp/Antholz/GH060140/part-0.mp4' -map_metadata 0 -metadata:s:v rotate="180" -codec copy '/home/kk/Videos/tmp/Antholz/GH060140/part-0-r.mp4'
        file_name_rotate = file_name.replace(MP4, 'rotate.' + MP4)
        params = [FFMPEG, '-i', file_name, '-map_metadata', '0', '-metadata:s:v:0', 'rotate=0', '-c', 'copy', '-y', file_name_rotate]
        rc = call_prog(params)

        print_log(f"Rotating output {file_name} to {file_name_rotate} returncode: {rc}")
        if rc != 0:
            exit()

        return file_name_rotate
    else:
        return file_name


def call_prog(params):
    print_log(str(params))
    process = Popen(params, stdout = PIPE, stderr = PIPE, encoding = 'utf8')
    while True:
        output = process.stderr.readline()
        if len(output) == 0 and process.poll() is not None:
            break
        if output:
            print_log(output.strip())
    rc = process.poll()
    return rc


def create_ovl_imgs(points, start_time):
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
    for act_sec in range(len(gps_points)):
        create_ovl_img(gps_points, start_time, act_sec)


def get_nearest_gps_datum(points, p_index, curr_time_rounded):
    dist_sec_last = abs((points[p_index].time - curr_time_rounded).total_seconds())
    dist_sec_curr = dist_sec_last
    while dist_sec_curr <= dist_sec_last:
        p_index += 1
        dist_sec_last = dist_sec_curr
        dist_sec_curr = abs((points[p_index].time - curr_time_rounded).total_seconds())

    return p_index - 1, dist_sec_last


def create_ovl_video():
    global base_name
    list_all_images = sorted(Path(img_dir).iterdir())
    base_name_time_part = list_all_images[0].name.replace(PNG, "")
    base_name = f'{base_name_time_part}_{args.outputname}'
    video_parts_out = list()
    chunk_size = 290
    chunk_size = 8
    beg = 0
    chunks = chunker(list_all_images, chunk_size)  # need more than 1 chunks because of ffmpeg/my computer could not handle more streams
    for index, chunk in enumerate(chunks):
        list_images = create_list_images(chunk)
        filter_list = list()
        for i in range(len(chunk)):
            filter_list.append(f"[v{i}][{i+1}:v] overlay=0:{ovl_pos_y}:enable='between(t,{i},{i+1})'[v{i+1}]")
        filter_complex = ";\n".join(filter_list)
        p = re.compile('^\[v0\](.*)\[v\d+\]$', re.DOTALL)  # @UndefinedVariable only for PyDev
        m = p.match(filter_complex)
        out_filter = out_file_base_tmp + "/filter"
        print_log(f"Writing output temp filter to {out_filter}")
        with open(out_filter, "w") as fd:
            print('[0:v]' + m.group(1), file = fd)

    #    ffmpeg -y -i input.mp4 -filter_complex_script "myscript.txt" -c:v libx264 output.mp4
        # out_video_name = f'{temp_dir}/part-{str(index)}'
        out_video_part_mp4 = f'{out_file_base_tmp}/part.mp4'
        dur = str(len(chunk))
        params = [FFMPEG, '-threads', '16', '-y', '-ss', str(beg), '-t', str(dur), '-i', concat_file, *list_images, '-filter_complex_script', out_filter, '-pix_fmt', 'yuv420p', '-c:a', 'copy', out_video_part_mp4]
        rc = call_prog(params)
        print_log(f"Writing output temp_dir to {out_video_part_mp4} returncode: {rc}")
        if rc != 0:
            exit()
        out_video_part = f'{out_file_base_tmp}/part-{str(index)}.ts'
        params = [FFMPEG, '-threads', '16', '-y', '-i', out_video_part_mp4, '-c', 'copy', out_video_part]
        rc = call_prog(params)
        print_log(f"Writing output temp_dir to {out_video_part} returncode: {rc}")
        if rc != 0:
            exit()
        video_parts_out.append(out_video_part)
        beg += chunk_size

    concat_video(video_parts_out, f'{out_file_base}/{base_name}.{MP4}')


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
    params = [FFMPEG, '-threads', '16', '-y', '-safe', '0', '-f', 'concat', '-segment_time_metadata', '1', '-i', video_file_list, '-vf', 'select=concatdec_select', '-af', 'aselect=concatdec_select,aresample=async=1', '-map', '0', concat_file_result]
    # concat_file_result_list = "concat:" + "|".join(video_parts)
    # params = [FFMPEG, '-threads', '16', '-y', '-i', concat_file_result_list, '-map', '0', '-c', 'copy', concat_file_result]
    rc = call_prog(params)
    print_log(f"Concatenated to {concat_file_result} returncode: {rc}")
    if rc != 0:
        exit()
    return concat_file_result


def make_img(time, act_sec, text0, text1):
    # make a blank image for the text, initialized to transparent text color
    txt = Image.new('RGBA', ovl_size, (0, 0, 0, 0))
# get a font
    fontname = 'Roboto-Bold.ttf'
    fontsize = 18
    fnt = ImageFont.truetype(fontname, fontsize)  # get a drawing context
    d = ImageDraw.Draw(txt)
# draw text, full opacity
    if timezone:
        time_str = timezone.fromutc(time).strftime("%Y.%m.%d %H:%M:%S")
    else:
        time_str = time.strftime("%Y.%m.%d %H:%M:%S")
    colorText = get_text_color(act_sec)
    if args.upovl:
        line1 = time_str
        line2 = text0
        line3 = text1
    else:
        line1 = text0
        line2 = text1
        line3 = time_str

    d.text((7, 10), line1, font = fnt, fill = colorText)
    d.text((7, 35), line2, font = fnt, fill = colorText)
    d.text((7, 60), line3, font = fnt, fill = colorText)
    txt.save(f"{img_dir}/{time_str}{PNG}")


def get_text_color (act_sec):
    image_file = f"{text_corner_dir}/{(act_sec+1):04d}.bmp"
    img = Image.open(image_file)

    img_size = img.size
    w_img = img_size[0]
    h_img = img_size[1]
    w_ovl = ovl_size[0]
    h_ovl = ovl_size[1]
    # print(img_size)

    if args.upovl:
        if args.rotate:
            text_corner = np.asarray(img)[h_img - h_ovl:h_img, w_img - w_ovl:w_img]
        else:
            text_corner = np.asarray(img)[0:h_ovl, 0:w_ovl]
    else:
        if args.rotate:
            text_corner = np.asarray(img)[0:h_ovl, w_img - w_ovl:w_img]
        else:
            text_corner = np.asarray(img)[h_img - h_ovl:h_img, 0:w_ovl]
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
        return (255, 255, 255, 255)
    else:
        return (0, 0, 0, 255)


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
    params = [FFMPEG, '-threads', '16', '-y', '-ss', beg, '-t', dur, '-i', video_file_name_rot, '-map', '0:0', '-map', '0:1', '-map', '0:3', '-c', 'copy', '-copyts', out_video_part_ts]
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
    parser.add_argument("-u", "--upovl", help = "overlay left up°, boolean", default = False)
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
    ovl_pos_y = 990
    # ovl_pos_y = 2060
    # ovl_pos_y = 1430
    ovl_size = (200, 90)
    start = datetime.datetime.now()
    out_file_base = f'{args.outdir}pgovl/{args.dir.split("/")[-1]}/{args.outputname}'
    log_file = out_file_base + "/log"
    out_file_base_tmp = out_file_base + "/tmp"
    tmp_video_dir_inp = out_file_base_tmp + '/inp/'
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
            start_time_rounded = datetime.datetime.fromtimestamp(round(start_time.timestamp()))
            create_ovl_imgs(points, start_time_rounded)
            create_ovl_video()
            new_dir = f'{args.outdir}ovl/{base_name}'
            shutil.move(out_file_base, new_dir)
            shutil.rmtree(f'{new_dir}/tmp')

        dur = datetime.datetime.now()
        process_duration = (dur - start).total_seconds()
        print_time(process_duration, "process")

