'''
Created on 2024. 8. 14.
A GOPRO SD kártya tartalmának csoportosítása
@author: kk
'''
import glob
import os
import shutil
from subprocess import Popen, PIPE

root_dir = '/run/media/kk/CrucialX9/Videos/GOPRO8/input/0130/'
root_dir = '/run/media/kk/CrucialX9/Videos/GOPRO8/100GOPRO/'
root_dir = '/home/kk/Videos/GOPRO/100GOPRO/'
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


def ovl_rename():
    root_dir = '/run/media/kk/CrucialX9/Videos/ovl/'
    MP4 = 'MP4'

    for ovl_file_path in sorted(glob.glob(root_dir + '*/*ovl.MP4')):
        curr_dir = os.path.dirname(ovl_file_path)
        ovl_file_name = os.path.basename(ovl_file_path)
        base_name = os.path.basename(curr_dir)
        concat_name = f'{base_name}_concat'
        shutil.move(f'{curr_dir}/{base_name}.{MP4}', f'{curr_dir}/{concat_name}.{MP4}')
        shutil.move(f'{curr_dir}/{ovl_file_name}', f'{curr_dir}/{base_name}.{MP4}')
        # shutil.move(f'{curr_dir}/subtitle.ass', f'{curr_dir}/{base_name}_subtitle.ass')
        # shutil.move(f'{curr_dir}/gpmf.bin', f'{curr_dir}/{base_name}_gpmf.bin')
        # shutil.move(f'{curr_dir}/gpmf.klv', f'{curr_dir}/{base_name}_gpmf.klv')
        # shutil.move(f'{curr_dir}/gpmf.gpx', f'{curr_dir}/{base_name}.gpx')
        # shutil.move(f'{curr_dir}/gpmf.kml', f'{curr_dir}/{base_name}.kml')
        print(ovl_file_path)


print("kész")
