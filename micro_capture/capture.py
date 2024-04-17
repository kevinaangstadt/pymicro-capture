import logging

from leica import LeicaEZ4HD

logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

microscope = LeicaEZ4HD()

microscope.capture_image("test.jpg", 2000)