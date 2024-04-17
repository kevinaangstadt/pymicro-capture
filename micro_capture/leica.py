# Interacting with Leica microscope

import enum
import logging
import os
import struct
import time

if os.name == 'nt':
    import libusb_package

import usb.core
import usb.util

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

        if os.name == 'nt':
            self.dev = libusb_package.find(idVendor=idVendor, idProduct=idProduct)
        else:
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
            logger.debug("%s: %s %s", hex(int.from_bytes(resp, "big")),
                  flags.capture_sequence, flags.capture_status)
            if flags.capture_status == capture_status:
                break
            time.sleep(sleep/1000)

    def _wait_for_capture_sequence(self, capture_sequence, sleep=0):
        while True:
            # read from 0xd000 4 bytes
            resp = self.dev.ctrl_transfer(URB_IN, 0x01, 0xd000, 0x0000, 0x0004)
            flags = CaptureStatusFlags(resp)
            logger.debug("%s: %s %s", hex(int.from_bytes(resp, "big")),
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
        logger.debug("image size: %d", image_size)

        # transmit the image data
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xae00, 0x0000, struct.pack("<H", 1))
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0xb200, 0x0000, struct.pack("<H", 1))
        self. dev.ctrl_transfer(URB_OUT, 0x01, 0x9300, 0x0000)

        # track how much we have left to transfer
        data_size = image_size # - final_block_size
        image_data = bytearray()

        max_read_size = 102400
        buf = usb.util.create_buffer(max_read_size)
        while data_size > 0:
            try:
                read_length = self.dev.read(0x81, buf)
            except usb.core.USBTimeoutError:
                logger.debug("File transfer timed out")
                # check if the last two bytes conclude the image data
                if image_data[-2] == 0xff and image_data[-1] == 0xd9:
                    logger.debug("found end of image")
                else:
                    logger.warning("Data transfer timed out, but did not find end of image. File may be incomplete.")
                # escape data capute
                break

            image_data.extend(buf[:read_length])
            data_size -= read_length
            logger.debug("%d bytes read; %d bytes left to read", read_length, data_size)

        # assert len(image_data) == image_size

        self._wait_for_capture_status(CaptureStatus.NO_IMG, 50)
        self.dev.ctrl_transfer(URB_OUT, 0x01, 0x1f30, 0x0000)
        self._wait_for_capture_sequence(CaptureSequence.IDLE, 50)
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