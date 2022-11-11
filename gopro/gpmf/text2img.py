#!/usr/bin/env python3

'''
Created on 2020. máj. 24.

@author: kk
'''

from PIL import Image, ImageDraw, ImageFont  # @UnresolvedImport only for PyDev
import numpy as np

ovl_size = (200, 90)
# base = Image.open('/home/kk/tmp/vlcsnap-2020-05-24-11h36m30s333.png').convert('RGBA')

fontname = 'Roboto-Bold.ttf'
fontsize = 18   
Text0 = "25km/h  123°  +2,5m/s"
Text1 = "2020.05.23 09:08:"
# images = []

def make_img(img_dir, out_file_base_tmp, time, timezone, act_sec, text0, text1):
    # make a blank image for the text, initialized to transparent text color
    txt = Image.new('RGBA', ovl_size, (0, 0, 0, 0))
# get a font
    fontname = 'Roboto-Bold.ttf'
    fontsize = 18   
    fnt = ImageFont.truetype(fontname, fontsize) # get a drawing context
    d = ImageDraw.Draw(txt)
# draw text, full opacity
    time_str = timezone.fromutc(time).strftime("%Y.%m.%d %H:%M:%S")
    colorText = get_text_color (time, act_sec, out_file_base_tmp)
    d.text((7, 10), text0, font=fnt, fill=colorText)
    d.text((7, 35), text1, font=fnt, fill=colorText)
    d.text((7, 60), time_str, font=fnt, fill=colorText)
    txt.save(f"{img_dir}/{time_str}.png")


def get_text_color (time, act_sec, out_file_base_tmp):
    image_file = f"{out_file_base_tmp}/{act_sec:04d}.bmp"
    img = Image.open(image_file)
    
    img_size = img.size
    w = img_size[0]
    h = img_size[1]
    # print(img_size)    
    
    left_down = np.asarray(img)[h-ovl_size[1]:h, 0:ovl_size[0]]
    # ld_img= Image.fromarray(left_down)
    # ld_img.show()
    
    rgb_result=np.array([0., 0., 0.])
    for line in left_down:
        rgb_line=np.array([0., 0., 0.])
        for rgb in line:
            rgb_px = np.array(rgb)
            rgb_line += rgb_px
        rgb_result += rgb_line / line.shape[0]
        
    rgb_result = rgb_result / left_down.shape[0]
    brightness = rgb_result[0]*0.299 + rgb_result[1]*0.587 + rgb_result[2]*0.114
    goproovl.print_log(f"act_sec {act_sec} RGB {rgb_result} brightness {brightness}")
    if brightness < 128:
        return (255,255,255,255)
    else:
        return (0,0,0,255)
    
# def make_overlay():
#     for i in range(20,31):
#         make_img(i, Text0, Text1, Text2 + str(i))

#     images.append(txt)
#txt.show()

#make_overlay()
#out = Image.alpha_composite(base, txt)

#out.save("/home/kk/image.png")
#out.show()
# images[0].save('/home/kk/Videos/tmp/anitest.gif',
#                'GIF',
#                save_all=True,
#                append_images=images[1:],
#                duration=1000, 
#                transparency=255, disposal=2)

