"""Blank-frame guard: featureless captures (black-out key, ended slideshow)
must be dropped; real slides — even letterboxed ones — must never be."""
from PIL import Image, ImageDraw

from modules.capture.daemon import CaptureDaemon

# _is_blank_frame doesn't touch self — call it unbound.
is_blank = lambda img: CaptureDaemon._is_blank_frame(None, img)


def test_pure_black_is_blank():
    assert is_blank(Image.new("RGB", (1920, 1200), (0, 0, 0)))


def test_pure_white_is_blank():
    assert is_blank(Image.new("RGB", (1920, 1200), (255, 255, 255)))


def test_solid_color_is_blank():
    assert is_blank(Image.new("RGB", (1920, 1200), (16, 16, 23)))


def test_real_slide_is_not_blank():
    im = Image.new("RGB", (1920, 1200), (255, 255, 255))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 80, 1920, 200], fill=(0, 128, 128))
    d.rectangle([300, 400, 1500, 460], fill=(20, 20, 20))
    assert not is_blank(im)


def test_letterboxed_slide_is_not_blank():
    """A 4:3 deck on a 16:10 screen has big black side bars — still a slide."""
    im = Image.new("RGB", (1920, 1200), (0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([320, 0, 1600, 1200], fill=(250, 250, 250))
    d.rectangle([500, 300, 1400, 380], fill=(0, 100, 150))
    assert not is_blank(im)


def test_failsafe_keeps_frame_on_error():
    assert CaptureDaemon._is_blank_frame(None, None) is False
