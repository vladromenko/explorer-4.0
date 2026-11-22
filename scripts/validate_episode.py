"""Read a recorded episode; never open hardware."""
import argparse
from explorer4.validation import validate

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('episode_id')
    validate(parser.parse_args().episode_id)
