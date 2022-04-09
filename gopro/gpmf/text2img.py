'''
Created on 2020. máj. 24.

@author: kk
'''

from PIL import Image, ImageDraw, ImageFont  # @UnresolvedImport only for PyDev

size = (200, 90)
# base = Image.open('/home/kk/tmp/vlcsnap-2020-05-24-11h36m30s333.png').convert('RGBA')

colorText = (255,0,0,255)
fontname = 'Roboto-Bold.ttf'
fontsize = 16   
Text0 = "25km/h  123°  +2,5m/s"
Text1 = "2020.05.23 09:08:"
# images = []

def make_img(img_dir, i, text0, text1, text2):
    # make a blank image for the text, initialized to transparent text color
    txt = Image.new('RGBA', size, (0, 0, 0, 0))
# get a font
    fnt = ImageFont.truetype(fontname, fontsize) # get a drawing context
    d = ImageDraw.Draw(txt)
# draw text, full opacity
    d.text((7, 10), text0, font=fnt, fill=colorText)
    d.text((7, 35), text1, font=fnt, fill=colorText)
    d.text((7, 60), text2, font=fnt, fill=colorText)
    txt.save(f"{img_dir}/{i}.png")

def make_overlay():
    for i in range(20,31):
        make_img(i, Text0, Text1, Text2 + str(i))
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

