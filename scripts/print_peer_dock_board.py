"""Render the survey board as a vector A4 PDF, preserving physical dimensions at 100% print scale."""
import argparse
import subprocess
from pathlib import Path

import cv2
from explorer4.peer_dock_config import DICTIONARY, MARKER_ID, MARKER_SIDE_M, WITNESS_ID, WITNESS_SIDE_M, WITNESS_OFFSET_DOWN_M


def render(destination):
    sheet = ['%!PS-Adobe-3.0','<< /PageSize [595.27559055 841.88976378] >> setpagedevice',
             '72 25.4 div dup scale','/Helvetica findfont 3.2 scalefont setfont',
             '15 286 moveto (Explorer 4.0  |  Cooperative docking  |  Print A4 at 100%) show']
    dictionary = cv2.aruco.getPredefinedDictionary(getattr(cv2.aruco,DICTIONARY))
    for ident,side,center_y in [(MARKER_ID,MARKER_SIDE_M*1000,187),(WITNESS_ID,WITNESS_SIDE_M*1000,187-1000*WITNESS_OFFSET_DOWN_M)]:
        cells = cv2.aruco.generateImageMarker(dictionary,ident,6)
        for row in range(6):
            for col in range(6):
                if cells[row,col]==0:
                    x=105-side/2+col*side/6
                    y=center_y+side/2-(row+1)*side/6
                    sheet.append(f'{x:g} {y:g} {side/6:g} {side/6:g} rectfill')
    sheet += ['15 25 moveto (Primary 7: 180 mm black edge. Witness 43: 36 mm. Centre spacing: 129 mm.) show',
              '15 18 moveto (Mount vertically. Measure the primary edge after printing.) show','showpage']
    subprocess.run(['ps2pdf','-dAutoRotatePages=/None','-',str(destination)],input='\n'.join(sheet).encode(),check=True)


if __name__=='__main__':
    a=argparse.ArgumentParser()
    a.add_argument('output',type=Path)
    render(a.parse_args().output)
