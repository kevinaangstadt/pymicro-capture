import logging
import os
import time

from printrun.printcore import printcore

from leica import LeicaEZ4HD

logger = logging.getLogger(__name__)


class MicroCapture:
    def __init__(self, device, baudrate):
        self.device = device
        self.baudrate = baudrate

        self.stage = printcore(self.device, self.baudrate)

        self.microscope = LeicaEZ4HD()

        while not self.stage.online:
            time.sleep(0.1)

    def connect(self):
        self.stage.connect()

        while not self.stage.online:
            time.sleep(0.1)

    def disconnect(self):
        self.stage.disconnect()
    
    def compute_auto_exposure(self, duration=10):
        """
        Compute auto exposure for the microscope. This will set the exposure
        time to the duration specified and capture an image. The image will be
        saved to the output directory.
        """
        logger.info("Computing auto exposure")
        self.microscope.compute_auto_exposure(duration)
        logger.info("Auto exposure computed")

    def capture(self, x_steps, x_step_size, y_steps, y_step_size, output_dir, feedrate=300):
        if not self.stage.printer:
            self.connect()

        self.stage.send("G91")
        self.stage.send(f"G0 F{feedrate}")
        self.stage.send("G0 X0 Y0")

        # Add a 20% buffer to the pause factor
        pause_factor = 60 / feedrate * 1.2

        for y in range(y_steps):
            for x in range(x_steps):
                col = x if y % 2 == 0 else x_steps - x - 1
                filename = os.path.join(
                    output_dir, f"img_r{y:03}_c{col:03}.jpg")
                self.microscope.capture_image(filename)

                logger.info(f"Captured image at row {y} column {col}")

                # move all but the last step in the x direction
                if x < x_steps - 1:
                    logger.debug(f"Moving to next column {col}")
                    # we are going to do a zig-zag pattern so this is go negative on
                    # even rows, go positive on odd rows
                    if y % 2 == 0:
                        self.stage.send(f"G0 X-{x_step_size}")
                    else:
                        self.stage.send(f"G0 X{x_step_size}")

                    time.sleep(pause_factor*x_step_size)

            # move in the y direction all but the last iteration
            logger.debug(f"Moving to next row {y}")
            if y < y_steps - 1:
                self.stage.send(f"G0 Y-{y_step_size}")
                time.sleep(pause_factor*y_step_size)

    def __del__(self):
        self.disconnect()


if __name__ == '__main__':
    import argparse

    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

    parser = argparse.ArgumentParser(
        description='Capture a grid of images from a microscope')
    
    parser.add_argument('--device', '-d', type=str,
                         required=True, help='Device path for microscope stage')
    parser.add_argument('--baudrate', '-b', type=int,
                         default=115200, help='Baudrate for microscope stage')


    subparsers = parser.add_subparsers(dest="command", help="sub-command help")

    capture = subparsers.add_parser('capture', help='Capture images')
    capture.add_argument('--output-dir', '-o', help='Output directory')
    capture.add_argument('--x-steps', '-x', type=int, required=True,
                         help='Number of steps in the x direction')
    capture.add_argument('--x-step-size', '-n', type=float,
                         required=True, help='Number of mm to move in the x direction')
    capture.add_argument('--y-steps', '-y', type=int, required=True,
                         help='Number of steps in the y direction')
    capture.add_argument('--y-step-size', '-m', type=float,
                         required=True, help='Number of mm to move in the y direction')
    

    expose = subparsers.add_parser('expose', help='Compute auto exposure')
    expose.add_argument('--duration', '-e', type=int, default=10,
                        help='Duration in seconds to capture the scene for auto exposure')

    args = parser.parse_args()

    m = MicroCapture(args.device, args.baudrate)

    if args.command == "capture":        
        m.capture(args.x_steps, args.x_step_size, args.y_steps, args.y_step_size, args.output_dir)

    elif args.command == "expose":
        m.compute_auto_exposure(args.duration)
    
    m.disconnect()