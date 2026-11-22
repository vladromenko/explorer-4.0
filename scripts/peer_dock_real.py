"""Capture passive field evidence or calibrate from an operator-surveyed board pose."""
import argparse
import json

from explorer4.peer_dock_real import calibrate, record


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    capture=sub.add_parser('observe')
    capture.add_argument('--url',default='http://127.0.0.1:8030',help='Active Explorer UI holding the shared lidar map')
    capture.add_argument('--standalone',action='store_true',help='Read-only raw images without a live shared map')
    for name in ('fit','validate'):
        p=sub.add_parser(name)
        p.add_argument('capture_id');p.add_argument('robot',choices=('tank','rosmaster'))
        p.add_argument('x',type=float);p.add_argument('y',type=float);p.add_argument('z',type=float)
        p.add_argument('outward_deg',type=float);p.add_argument('--valid-hours',type=float,default=8)
    args=parser.parse_args()
    if args.command=='observe':
        if args.standalone:
            result=record()
        else:
            import httpx
            response=httpx.post(args.url.rstrip('/')+'/api/peer-dock/observe',timeout=20,trust_env=False)
            response.raise_for_status()
            result=response.json()
    else:
        result=calibrate(args.capture_id,args.robot,[args.x,args.y,args.z],args.outward_deg,validate=args.command=='validate',valid_hours=args.valid_hours)
    print(json.dumps(result,indent=2,ensure_ascii=False))
