from PIL import Image, ImageDraw, ImageFont
from gpmf import goproovl

min_hight = 159
max_hight = 1020
elev_img_size = (280, 120)
buffer = 5
fontname = 'DejaVuSans.ttf'
fontsize = 8
fnt = ImageFont.truetype(fontname, fontsize)


def create_img_test():
    create_img(159, 1020)
    create_img(159, 2020)
    create_img(159, 2720)
    create_img(159, 3020)
    create_img(319, 423)


def create_img(min_hight, max_hight):
    lines, step, main_step = goproovl.create_elevation_niveau_lines(min_hight, max_hight, elev_img_size, buffer)
    print(len(lines))
    img = Image.new('RGBA', elev_img_size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0, 0), elev_img_size], fill = (0, 0, 0, 50), outline = (0, 0, 0, 100), width = 1)

    for line_dict in lines:
        line_width = 2 if line_dict["niveau"] * step % main_step == 0 else 1
        draw.line(line_dict["line"], fill = (55, 55, 55), width = line_width)
        draw.text((0, line_dict["hight"] - 5), str(int(line_dict["niveau"] * step)), font = fnt, fill = (55, 55, 55))
    img.show()
    img.save(f'/home/kk/tmp/img_{min_hight}-{max_hight}.png')


if __name__ == "__main__":
    create_img_test()

