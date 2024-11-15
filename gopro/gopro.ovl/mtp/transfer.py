'''
Created on 2020. júl. 28.

@author: kk
'''

import mtpy

devices = mtpy.get_raw_devices()
if len(devices) != 1:
    print(f"devices={str(devices)}")

dev = mtpy.get_raw_devices()[0].open()
children = dev.get_children()
for child in children:
    print(f"child={str(child)}")

p = dev.get_descendant_by_path("/DCIM/100GOPRO")

print(f"p={str(p)}")

print("OK")