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
import glob
from io import BytesIO
import math
import os
from pathlib import Path
import re
import shutil
import struct
from subprocess import Popen, PIPE

from PIL import Image, ImageDraw, ImageFont  # @UnresolvedImport only for PyDev
from google.protobuf import duration_pb2
import pytz
from tzwhere import tzwhere  # https://github.com/pegler/pytzwhere/issues/53

import numpy as np

FFMPEG = "/usr/bin/ffmpeg"
FFPROBE = "/usr/bin/ffprobe"
GPSFREQU = 18
MP4 = 'MP4'
PNG = '.png'


def time_in_sec(min_sec):
    duration = str(min_sec).split(":")
    seconds = float(duration[-1])
    if len(duration) > 1:
        seconds += 60 * int(duration[-2])
    return seconds


def dump_metadata(filename):
    proc = Popen([FFPROBE, filename], stdout = PIPE, stderr = PIPE, encoding = 'utf8')
    global duration_sec
    global ovl_pos_y
    for line in list(proc.stderr):
        print_log(line)
        m = re.match(".*Duration: ([^,]+),.*", line)
        if m:
            duration_sec = time_in_sec(m.group(1))
        m = re.match(".*Stream #0:0.*, \d+x(\d+) .*", line)
        if m:
            if args.upovl:
                ovl_pos_y = 0
            else:
                ovl_pos_y = int(m.group(1)) - ovl_size[1]
    print_time(duration_sec, "temp_dir")

    proc = Popen([FFMPEG, '-i', filename, '-vf', 'fps=1', out_file_text_corner_tmp + '/%04d.bmp'], stdout = PIPE, stderr = PIPE, encoding = 'utf8')  # frames per second (for calculate text color)
    for line in list(proc.stderr):
        print_log(line)

    (o, e) = Popen([FFMPEG, '-y', '-i', filename, '-codec', 'copy', '-map', '0:3', '-f', 'rawvideo', '-'], stdout = PIPE, stderr = PIPE).communicate()
    Path(temp_dir + '/' + video_name + '.gpmf').write_bytes(o)

    return BytesIO(o)


def print_time(total_seconds, text):
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    print_log(f"{text} duration: {total_seconds:2.2f} sec:   {hours:.0f} h {minutes:.0f} m {seconds:2.2f} s")


def calc_vertical_speed(step, alt0, alt1):
    return (alt1 - alt0) / step


def getDst(gps_time):
    time = timezone.fromutc(gps_time)
    return time.strftime("%Y.%m.%d %H:%M:%S")


def calc_direction_ift(diff_sec, gps_datum_prev, gps_datum_next, text0, text1):
    direction = angle_from_coordinate(gps_datum_prev['latitude'], gps_datum_prev['longitude'], gps_datum_next['latitude'], gps_datum_next['longitude'])
    vertical_speed = calc_vertical_speed(diff_sec, gps_datum_prev['altitude'], gps_datum_next['altitude'])
    text0 += f'   {direction:.0f} °'
    text1 += f'   {vertical_speed:.1f} m/s'
    return text0, text1


def create_ovl_img(gps_datum_prev, gps_datum, gps_datum_next, act_sec):
    time = gps_datum['timestamp']
    if not gps_datum['diff_sec']:
        text0 = ''
        text1 = ''
    else:
        speed = 3.6 * gps_datum["speed3mps"]
        heigh = gps_datum["altitude"]
        text0 = f'{speed:.0f} km/h'
        text1 = f'{heigh:.0f} m'
        if gps_datum_prev and 'latitude' in gps_datum_prev and gps_datum_next and 'latitude' in gps_datum_next:
            text0, text1 = calc_direction_ift(gps_datum['diff_sec'], gps_datum_prev, gps_datum_next, text0, text1)
        elif gps_datum_prev and 'latitude' in gps_datum_prev:
            text0, text1 = calc_direction_ift(gps_datum['diff_sec'], gps_datum_prev, gps_datum, text0, text1)
        elif gps_datum_next and 'latitude' in gps_datum_next:
            text0, text1 = calc_direction_ift(gps_datum['diff_sec'], gps_datum, gps_datum_next, text0, text1)
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


def create_track(data, last_sec_part):
    global timezone
    csv_data = []
    first_gps_fix_time = None
    act_sec = None
    gps_points = list()
    for row in data:
#         try:
#             start_time = row['timestamp']
#         except KeyError:
#             if index == 0:
#                 # Let's just assume it's one second before the next
#                 # available timestamp.
#                 start_time = data[index + 1]['timestamp'] - datetime.timedelta(seconds=1)
#             else:
#                 raise
#         if index == len(data) - 1:
#             end_time = start_time + datetime.timedelta(seconds=1)
#         else:
#             end_time = data[index + 1]['timestamp']
#         length_row = len(row['gps_data'])
        gps_data = row['gps_data']
        print_log(f"gps_data: {gps_data}")
        if len(gps_data) > 0:
            gps_datum = gps_data[0]
            if gps_datum["fix"] > 0 and not (gps_datum["latitude"] == 0 and gps_datum["longitude"] == 0):
                if not first_gps_fix_time:
                    timezone_str = tzwhere.tzwhere().tzNameAt(gps_datum["latitude"], gps_datum["longitude"])
                    if timezone_str:
                        timezone = pytz.timezone(timezone_str)
                        first_gps_fix_time = row['timestamp']
                        act_sec = first_gps_fix_time.replace(microsecond = 0) - datetime.timedelta(seconds = 1)
                if act_sec:
                    diff_sec = (row['timestamp'] - act_sec).total_seconds()
                    if diff_sec >= 1:
                        for i in range(1, int(diff_sec)):  # gap without gps fix
                            act_sec += datetime.timedelta(seconds = 1)
                            gps_datum_temp = {}
                            gps_datum_temp['timestamp'] = act_sec
                            gps_datum_temp['diff_sec'] = None
                            gps_points.append((gps_datum_temp))
                        act_sec = row['timestamp'].replace(microsecond = 0)
                        gps_datum['timestamp'] = act_sec
                        gps_datum['diff_sec'] = diff_sec
                        csv_data.append(gps_datum)
                        gps_points.append((gps_datum))

    if first_gps_fix_time:
        gps_fix_total_seconds = (row['timestamp'] - first_gps_fix_time).total_seconds()
        print_time(gps_fix_total_seconds, "gps fix")
        gps_fix_diff = duration_sec - gps_fix_total_seconds - last_sec_part
        if gps_fix_diff < 0:
            gps_fix_diff = 0
        print_time(gps_fix_diff, "begin - gps fix difference")
        create_pre_imgs(first_gps_fix_time, gps_fix_diff)

        for i, gps_datum in enumerate(gps_points):
            gps_datum_prev = gps_points[i - 1] if i > 0 else None
            gps_datum_next = gps_points[i + 1] if i + 1 < len(gps_points) else None
            act_sec = (gps_datum['timestamp'] - first_gps_fix_time).total_seconds() + gps_fix_diff
            if act_sec > math.floor(duration_sec):
                act_sec -= 1
            if act_sec > begin and (end == 0 or act_sec <= end):
                create_ovl_img(gps_datum_prev, gps_datum, gps_datum_next, math.floor(act_sec) + 1)
    else:
        print_log("nincs gps adat")
        create_pre_imgs(row['timestamp'], duration_sec)
        csv_data.append(row)

    return csv_data


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


def create_ovl_video():
    global base_name_time_part
    video_file_name_rot = rotate(video_file_name)
    list_all_images = sorted(Path(img_dir).iterdir())
    base_name_time_part_file = f'{out_file_base_tmp}/base_name_time_part'
    if not base_name_time_part:
        if os.path.exists(base_name_time_part_file):
            with open(base_name_time_part_file, "r") as bnfd:
                base_name_time_part = bnfd.readline().replace('\n', '')
        else:
            base_name_time_part = list_all_images[0].name.replace(PNG, "")
            with open(base_name_time_part_file, "w") as bnfd:
                bnfd.write(base_name_time_part)
    chunk_size = 290
    end_sec = duration_sec if end == 0 else end
    rest = end_sec - begin
    beg = begin
    chunks = chunker(list_all_images, chunk_size)  # need more than 1 chunks because of ffmpeg/my computer could not handle more streams
    for index, chunk in enumerate(chunks):
        list_images = create_list_images(chunk)
        filter_list = list()
        for i in range(len(chunk)):
            filter_list.append(f"[v{i}][{i+1}:v] overlay=0:{ovl_pos_y}:enable='between(t,{i},{i+1})'[v{i+1}]")
        filter_complex = ";\n".join(filter_list)
        p = re.compile('^\[v0\](.*)\[v\d+\]$', re.DOTALL)  # @UndefinedVariable only for PyDev
        m = p.match(filter_complex)
        out_filter = temp_dir + "/filter"
        print_log(f"Writing output temp filter to {out_filter}")
        with open(out_filter, "w") as fd:
            print('[0:v]' + m.group(1), file = fd)

    #    ffmpeg -y -i input.mp4 -filter_complex_script "myscript.txt" -c:v libx264 output.mp4
        # out_video_name = f'{temp_dir}/part-{str(index)}'
        out_video_part_mp4 = f'{out_file_base_tmp}/part.mp4'
        dur = str(min(chunk_size, rest))
        params = [FFMPEG, '-threads', '16', '-y', '-ss', str(beg), '-t', str(dur), '-i', video_file_name_rot, *list_images, '-filter_complex_script', out_filter, '-pix_fmt', 'yuv420p', '-c:a', 'copy', out_video_part_mp4]
        rc = call_prog(params)
        print_log(f"Writing output temp_dir to {out_video_part_mp4} returncode: {rc}")
        if rc != 0:
            exit()
        out_video_part = f'{temp_dir}/part-{str(index)}.ts'
        params = [FFMPEG, '-threads', '16', '-y', '-i', out_video_part_mp4, '-c', 'copy', out_video_part]
        rc = call_prog(params)
        print_log(f"Writing output temp_dir to {out_video_part} returncode: {rc}")
        if rc != 0:
            exit()
        # with open(f'{out_video_name}.txt', "w") as text_file:
        #     print(out_video_part, file = text_file)
        #     print(dur, file = text_file)
        video_parts.append(out_video_part)
        beg += chunk_size
        rest -= chunk_size


def gopro_binary_to_csv(gopro_binary):
    """Essentially a reimplementation of
    https://github.com/JuanIrache/gopro-utils in python.

    Takes an output file location to write to. This will parse a GoPro
    binary data file, and turn it into a CSV we can use to load data.
    That binary data file can be created with:
        ffmpeg -y -i GOPR0001.MP4 -codec copy \
                -map 0:3 -f rawvideo GOPR0001.bin
    https://pastebin.com/raw/mqbKKeSn
    """
    label_length = 4
    desc_length = 4
    # Set default scale values so we can always use it.
    scales = [1, 1, 1, 1]
    # Decide if we have a GPS fix and should start recording data.
    gps_fix = 0
    gps_accuracy = 9999
    okay_to_record = False
    data = []
    current_data = {}
    count = 0
    countGPS5 = 0
    countGPS5_per_GPSU = 0
    countGPSU = 0
    while True:
        count += 1
        try:
            label_string = str(gopro_binary.read(label_length))
            desc = struct.unpack('>cBBB', gopro_binary.read(desc_length))
            print_log("label_string: " + label_string)
            print_log("desc: " + str(desc))
        except struct.error as e:
            break
        # If the first byte of the description string is zero, there
        # is no length.
        data_type = desc[0]
        if data_type == b'\x00':
            continue
        # If the label is empty, skip a packet.
        if "EMPT" in label_string:
            gopro_binary.read(4)
            continue
        # Get the size and length of data.
        val_size = desc[1]
        num_values = desc[2] << 8 | desc[3]
        data_length = val_size * num_values

        if "SCAL" in label_string:
            # Get the scale to apply to subsequent values.
            scales = []
            for i in range(num_values):
                if val_size == 2:
                    scales.append(int(struct.unpack('>H', gopro_binary.read(2))[0]))
                elif val_size == 4:
                    scales.append(int(struct.unpack('>I', gopro_binary.read(4))[0]))
                else:
                    raise Exception("Unknown val_size for scales. Expected 2 or 4, got {}".format(val_size))
        else:
            for numvalue in range(num_values):
                value = gopro_binary.read(val_size)
                try:
                    if "GPS5" in label_string:
                        countGPS5 += 1
                        countGPS5_per_GPSU += 1
                        current_gps_data = {}
                        if val_size != 20:
                            raise Exception("Invalid data length for GPS5 data type. Expected 20 got {}.".format(val_size))
                        latitude, longitude, altitude, speed, speed3d = struct.unpack('>iiiii', value)
                        if okay_to_record:
                            current_gps_data["latitude"] = float(latitude) / scales[0]
                            current_gps_data["longitude"] = float(longitude) / scales[1]
                            current_gps_data["altitude"] = float(altitude) / scales[2]
                            current_gps_data["speedmps"] = float(speed) / scales[3]
                            current_gps_data["speed3mps"] = float(speed3d) / scales[4]
                            current_gps_data["fix"] = gps_fix
                            current_gps_data["accuracy"] = gps_accuracy
                            current_data["gps_data"].append(current_gps_data)
                    elif "GPSU" in label_string:
                        countGPSU += 1
                        countGPS5_per_GPSU = 0
                        # Only append to data if we have some GPS data.
                        timestamp = datetime.datetime.strptime(value.strip().decode(), '%y%m%d%H%M%S.%f')
                        print_log(f"gopro_binary_to_csv timestamp: {timestamp}")
                        current_data = {'timestamp': timestamp, 'gps_data': []}
                        data.append(current_data)
                    elif "GPSF" in label_string:
                        # GPS Fix. Per https://github.com/gopro/gpmf-parser:
                        # Within the GPS stream: 0 - no lock, 2 or 3 - 2D or 3D Lock.
                        gps_fix = int(struct.unpack('>I', value)[0])
                    elif 'GPSP' in label_string:
                        # GPS Accuracy. Per https://github.com/gopro/gpmf-parser:
                        # Within the GPS stream, under 500 is good.
                        gps_accuracy = int(struct.unpack('>H', value)[0])
    #                 elif 'STNM' in label_string:
                        # streem name
    #                     print_log("STNM: " + str(value))
                    else:
                        # Just skip on by the data_length, this is a data
                        # type we don't care about.
                        continue
                    # Decide whether we want to record data.
                    okay_to_record = gps_fix in [2, 3] and gps_accuracy < 500
                except ValueError as e:
                    print_log(f"gopro_binary_to_csv error: {e}")

        # Data is always packed to four bytes, so skip to the next
        # four byte chunk if we're not currently there.
        mod = data_length % 4
        if mod:
            gopro_binary.read(4 - mod)

    print_log(f"count: {count}")
    print_log(f"countGPS5: {countGPS5}")
    print_log(f"countGPSU: {countGPSU}")
    # Now we've got all the data, we need to populate timestamps.
    if not data:
        cts = os.path.getmtime(video_file_name)
        time = datetime.datetime.fromtimestamp(cts)  # - datetime.timedelta(seconds=duration_sec)
        current_data = {'timestamp': time, 'gps_data': []}
        data.append(current_data)

    csv_data = create_track(data, countGPS5_per_GPSU / GPSFREQU)
    create_ovl_video()

    return csv_data


def make_gpx(points, fd):
    print("""<?xml version="1.0" encoding="UTF-8"?>
<gpx xmlns="http://www.topografix.com/GPX/1/1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd" version="1.1" creator="gpmf.py">
 <trk>
  <trkseg>""",
        file = fd,
    )
    for p in points:
        if "latitude" in p:
            print(
                f'   <trkpt lat="{p["latitude"]}" lon="{p["longitude"]}"><ele>{p["altitude"]}</ele><time>{p["timestamp"].strftime("%Y-%m-%dT%H:%M:%SZ")}</time><fix>{p["fix"]}</fix><accuracy>{p["accuracy"]}</accuracy><speed>{p["speedmps"]}</speed><speed3d>{p["speed3mps"]}</speed3d></trkpt>',
                file = fd
            )
    print("""  </trkseg>
 </trk>
</gpx>
""",
        file = fd
    )


def print_log(param):
    string = str(datetime.datetime.now()) + " " + param.replace("\n", "")
    print(string)
    print(string, file = lfd, flush = True)


def concat_ovl_video():
    # video_file_list = out_file_base + "/files"
    # with open(video_file_list, "w") as fd:
    #     for file, dur in video_parts:
    #         print(f"file '{file}'", file = fd)
    #         print(f"duration {dur}", file = fd)
    # print_log(f"Writing video parts list to {video_file_list}")
    concat_file_list = "concat:" + "|".join(video_parts)
    result_video = f'{out_file_base}/{base_name}.mp4'
    # params = [FFMPEG, '-threads', '16', '-y', '-safe', '0', '-f', 'concat', '-segment_time_metadata', '1', '-i', video_file_list, '-vf', 'select=concatdec_select', '-af', 'aselect=concatdec_select,aresample=async=1', result_video]
    params = [FFMPEG, '-threads', '16', '-y', '-i', concat_file_list, '-c', 'copy', result_video]
    rc = call_prog(params)


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
    act_sec = max(1, act_sec)
    image_file = f"{out_file_text_corner_tmp}/{act_sec:04d}.bmp"
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
    base_name_time_part = None
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
    tmp_video_dirs = out_file_base_tmp + '/video_dirs/'
    os.makedirs(tmp_video_dirs, exist_ok = True)
    out_file_text_corner_tmp = out_file_base_tmp + '/tc'
    with open(log_file, "w+") as lfd:
        print_log(f"begin {args.begin}, end {args.end}")
        inp_video_files_all = sorted(Path(args.dir).iterdir())
        inp_video_files = None
        video_parts = list()
        if os.path.exists(out_file_base):
            tmp_dirs = sorted(Path(tmp_video_dirs).iterdir())
            tmp_dirs_ready = tmp_dirs[:len(tmp_dirs) - 1]
            if len(tmp_dirs_ready) > 0:
                inp_video_files_processed = inp_video_files_all[:len(tmp_dirs_ready)]
                for file in inp_video_files_processed:
                    print_log(f"file already processed {str(file)}")
                for tmp_dir in tmp_dirs_ready:
                    dur_files = glob.glob(f'{tmp_dir}/*.ts')
                    for dur_file in sorted(dur_files):
                        # part_name = str(out_video).split(".")[0]
                        # dur_file_text = Path(dur_file).read_text().split("\n")
                        # print_log(f"{str(dur_file_text)}")
                        # video_parts.append((dur_file_text[0], dur_file_text[1]))
                        video_parts.append(dur_file)

                inp_video_files = inp_video_files_all[len(tmp_dirs_ready):]
                shutil.rmtree(tmp_dirs[-1])
                args.begin = 0
            else:
                shutil.rmtree(out_file_base_tmp)
        os.makedirs(out_file_text_corner_tmp, exist_ok = True)

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
            print_log(f"Processing {video_file_name}")
            temp_dir = tmp_video_dirs + video_name
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            img_dir = temp_dir + "/images"
            os.makedirs(img_dir)
            if index == 0:
                begin = time_in_sec(args.begin)
            else:
                begin = 0
            if index + 1 == len(file_list) and args.end:
                end = time_in_sec(args.end)
            else:
                end = 0
            points.extend(gopro_binary_to_csv(dump_metadata(video_file_name)))
        # output a simple gpx
        if points:
            gpx_file = f'{out_file_base}/{args.outputname}.gpx'
            with open(gpx_file, "w+") as fd:
                print_log(f"Writing output gpx to {gpx_file}")
                make_gpx(points, fd)

            base_name = f'{base_name_time_part}_{args.outputname}'
            concat_ovl_video()
            new_dir = f'{args.outdir}ovl/{base_name}'
            shutil.move(out_file_base, new_dir)
            shutil.move(f'{new_dir}/log', f'{new_dir}/{base_name}.log')
            shutil.move(f'{new_dir}/{args.outputname}.gpx', f'{new_dir}/{base_name}.gpx')

        shutil.rmtree(f'{new_dir}/tmp')
        dur = datetime.datetime.now()
        process_duration = (dur - start).total_seconds()
        print_time(process_duration, "process")

