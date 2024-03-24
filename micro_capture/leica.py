# Interacting with Leica microscope

import enum
import logging
import struct
import time

import usb.core

logger = logging.getLogger(__name__)

class CaptureStatus(enum.IntFlag):
    IMG_READY = 0x04
    NO_IMG = 0x00


class CaptureSequence(enum.IntFlag):
    IDLE = 0x30
    READY = 0x40
    CAPTURING = 0x50
    CAPTURED = 0x80


class CaptureStatusFlags:
    def __init__(self, raw_status):
        _, self.capture_sequence, self.capture_status, _ = struct.unpack(
            ">BBBB", raw_status)
        self.capture_sequence = CaptureSequence(self.capture_sequence)
        self.capture_status = CaptureStatus(self.capture_status)


URB_OUT = 0x40
URB_IN = 0xc0


class LeicaEZ4HD:
    def __init__(self):
        idVendor = 0x1711
        idProduct = 0x3001

        self.dev = usb.core.find(idVendor=idVendor, idProduct=idProduct)
        if self.dev is None:
            raise ValueError("Device not found")

        self.dev.set_configuration()
        self.cfg = self.dev.get_active_configuration()

    def _wait_for_capture_status(self, capture_status, sleep=0):
        while True:
            # read from 0xd000 4 bytes
            resp = self.dev.ctrl_transfer(URB_IN, 0x01, 0xd000, 0x0000, 0x0004)
            flags = CaptureStatusFlags(resp)
            logger.debug(hex(int.from_bytes(resp, "big")),
                  flags.capture_sequence, flags.capture_status)
            if flags.capture_status == capture_status:
                break
            time.sleep(sleep/1000)

    def _wait_for_capture_sequence(self, capture_sequence, sleep=0):
        while True:
            # read from 0xd000 4 bytes
            resp = self.dev.ctrl_transfer(URB_IN, 0x01, 0xd000, 0x0000, 0x0004)
            flags = CaptureStatusFlags(resp)
            logger.debug(hex(int.from_bytes(resp, "big")),
                  flags.capture_sequence, flags.capture_status)
            if flags.capture_sequence == capture_sequence:
                break
            time.sleep(sleep/1000)

    def compute_auto_exposure(self, duration=10):
        """
        Compute auto exposure for the microscope. This will set the exposure
        duration and gain based on capturing the current scene for the given
        duration (default: 10s).
        :param duration: Duration in seconds to capture the scene for auto 
                         (default: 10s)
        :return: None
        """
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f30, 0x0000)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xf0001, 0x0000)
        self.dev.clear_halt(0x81)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f70, 0x0000)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xe109, 0x0000)
        self.dev.ctrl_transfer(URB_IN, 0x01, 0x6400, 0x0000, 2)

        time.sleep(10)

        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f30, 0x0000)

        while True:
            try:
                resp = self.dev.read(0x81, 512)
            except usb.core.USBTimeoutError:
                break
    
    def _perform_capture(self):
        self.dev.ctrl_transfer(URB_IN, 0x01, 0x6400, 0x0000, 2)
        self.dev.ctrl_transfer(URB_IN, 0x01, 0x6400, 0x0000, 2)

        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xe100, 0x0000)
        self.dev.ctrl_transfer(URB_IN, 0x01, 0x6400, 0x0000, 2)


        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f30, 0x0000)

        self._wait_for_capture_status(CaptureStatus.NO_IMG, 10)

        self.dev.ctrl_transfer(URB_IN, 0x01, 0xba00, 0x00c0, 2)

        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xeb00, 0x0000, struct.pack("<H", 1))
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xeb01, 0x0000, struct.pack("<H", 1))

        # set capture resolution to 2048x1536
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x4650, 0x0000, struct.pack("<HH", 2048, 1536))

        # trigger a switch to capture mode
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f40, 0x0000)

        logger.debug("waiting for ready")
        self._wait_for_capture_sequence(CaptureSequence.READY, 10)

        # trigger capture
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f50, 0x0000)

        logger.debug("waiting for capture to start")
        self._wait_for_capture_sequence(CaptureSequence.CAPTURING, 50)
        logger.debug("waiting for capture to finish")
        self._wait_for_capture_sequence(CaptureSequence.CAPTURED, 50)
        logger.debug("waiting for ready")
        self._wait_for_capture_sequence(CaptureSequence.READY, 50)


    def _transfer_image(self):
        logger.debug("waiting for image to be ready for transfer")
        self._wait_for_capture_status(CaptureStatus.IMG_READY, 50)

        logger.debug("reading image metadata")
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xae00, 0x0000, struct.pack("<H", 1))
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xb200, 0x0000, struct.pack("<H", 1))

        # read 64 bytes with the image size embedded
        resp = self.dev.ctrl_transfer(URB_IN, 0x01, 0xb900, 0x0000, 64)
        file_name, _, image_size, _ = struct.unpack("<16sIII", resp)
        logger.debug("image size:", image_size)

        # transmit the image data
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xae00, 0x0000, struct.pack("<H", 1))
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xb200, 0x0000, struct.pack("<H", 1))
        self. dev.ctrl_transfer(URB_OUT, 0x01, 0x9300, 0x0000)

        # track how much we have left to transfer
        data_size = image_size # - final_block_size
        image_data = bytearray()

        while data_size > 0:
            read_length = 102400
            resp = self.dev.read(0x81, read_length)
            image_data.extend(resp)
            data_size -= len(resp)

        assert len(image_data) == image_size

        self._wait_for_capture_status(CaptureStatus.NO_IMG, 10)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f30, 0x0000)
        self._wait_for_capture_sequence(CaptureSequence.IDLE, 10)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xf001, 0x0000)

        # dev.clear_halt(0x01)
        self.dev.clear_halt(0x81)

        return image_data


    def capture_image(self, filename):
        """
        Capture an image from the microscope and save it to the given filename.
        :param filename: Filename to save the captured image to
        :return: None
        """

        self._perform_capture()
        data = self._transfer_image()

        with open(filename, "wb") as f:
            f.write(data)