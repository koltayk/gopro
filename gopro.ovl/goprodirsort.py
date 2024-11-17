'''
Created on 2024. 8. 14.
A GOPRO SD kártya tartalmának csoportosítása
@author: kk
'''
import glob
import os
from subprocess import Popen, PIPE

root_dir = '/run/media/kk/CrucialX9/Videos/GOPRO8/100GOPRO/'
root_dir = '/run/media/kk/9C33-6BBD/DCIM/100GOPRO/'
link_dir = '/home/kk/Videos/GOPRO/'
for file_path in glob.iglob(root_dir + 'GH01*.MP4'):
    video_num = file_path[-8:-4]
    print(video_num)
    img_dir = link_dir + video_num
    os.makedirs(img_dir)
    for filename in glob.iglob(f'{root_dir}*{video_num}.MP4'):
        # print(filename)
        proc = Popen(['ln', '-s', filename, img_dir], stdout = PIPE, stderr = PIPE, encoding = 'utf8')  # symbolic link
        for line in list(proc.stderr):
            print(line)
    # find_gpx_track(file_path)

print("kész")
