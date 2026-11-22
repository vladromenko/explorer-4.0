"""An opaque freestanding screen almost flush with the docking station."""
import xml.etree.ElementTree as ET

import cv2
import numpy as np


def install_screen(tank):
    # A steel bracket mounted on the far side supports the plate. The centre
    # of the station remains accessible. All pieces have collision geometry.
    target = tank.find(".//body[@name='target']")
    body = ET.SubElement(target, 'body', name='dock_screen', pos='0 0 0')
    for name, pos, size in [
        ('plate', '-.166 0 0', '.006 .060 .105'),
        ('bracket', '-.166 .16 .111', '.009 .245 .007'),
        ('stand', '-.166 .394 -.045', '.012 .012 .155'),
    ]:
        ET.SubElement(body, 'geom', name='screen_' + name, type='box', pos=pos,
                      size=size, rgba='.10 .47 .40 1', contype='2', conaffinity='2')


def vary_screen(model, seed):
    # A parked screen is still physically present. Lateral placement changes
    # without altering the waypoint, robot starts or the camera mounting points.
    body = model.body('tank/dock_screen')
    shift = np.random.default_rng(seed + 3047).uniform(-.012, .012)
    body.pos[1] = (.068 if seed % 2 == 0 else .49) + shift


def screen_fraction(rgb):
    """Image-only cue. Use the fixed known coating on the freestanding screen."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (69, 72, 28), (94, 255, 248))
    height, width = mask.shape
    return float(np.mean(mask[height // 4:3 * height // 4, width // 4:3 * width // 4] > 0))
