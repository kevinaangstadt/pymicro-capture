import os
import time

from printrun.printcore import printcore

from leica import LeicaEZ4HD


class MicroCapture:
    def __init__(self, device, baudrate, output_dir):
        self.device = device
        self.baudrate = baudrate
        self.output_dir = output_dir

        self.stage = printcore(self.device, self.baudrate)

        self.microscope = LeicaEZ4HD()

        while not self.stage.online:
            time.sleep(0.1)

    def capture(self, x_steps, x_step_size, y_steps, y_step_size, feedrate=300):
        self.microscope.compute_auto_exposure()

        self.stage.send("G91")
        self.stage.send(f"G0 F{feedrate}")
        self.stage.send("G0 X0 Y0")

        # Add a 10% buffer to the pause factor
        pause_factor = 60 / feedrate * 1.1

        for y in range(y_steps):
            for x in range(x_steps):
                filename = os.path.join(self.output_dir, f"{x}_{y}.jpg")
                self.microscope.capture_image(filename)

                if x % 2 == 0:
                    self.stage.send(f"G0 X-{y_step_size}")
                else:
                    self.stage.send(f"G0 X{x_step_size}")
                
                time.sleep(pause_factor*x_step_size)

            self.stage.send(f"G0 Y-{x_step_size}")
            time.sleep(pause_factor*y_step_size)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Capture a grid of images from a microscope')
    parser.add_argument('--output-dir', '-o', help='Output directory')
    parser.add_argument('--x-steps', '-x', type=int, required=True,
                        help='Number of steps in the x direction')
    parser.add_argument('--x-step-size', '-n', type=float,
                        required=True, help='Number of mm to move in the x direction')
    parser.add_argument('--y-steps', '-y', type=int, required=True,
                        help='Number of steps in the y direction')
    parser.add_argument('--y-step-size', '-m', type=float,
                        required=True, help='Number of mm to move in the y direction')
    parser.add_argument('--device', '-d', type=str,
                        required=True, help='Device path for microscope stage')
    parser.add_argument('--baudrate', '-b', type=int,
                        default=115200, help='Baudrate for microscope stage')

    args = parser.parse_args()

    m = MicroCapture(args.device, args.baudrate, args.output_dir)
    m.capture(args.x_steps, args.x_step_size, args.y_steps, args.y_step_size)