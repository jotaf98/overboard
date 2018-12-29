
from PyQt5 import QtCore, QtWidgets

# needed right after QT imports for high-DPI screens
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
#QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

class Slider(QtWidgets.QSlider):
  """Slider that updates its value on mouse drag (not just click)"""
  def mousePressEvent(self, event):
    super(Slider, self).mousePressEvent(event)
    if event.button() == QtCore.Qt.LeftButton:
      val = self.pixelPosToRangeValue(event.pos())
      self.setValue(val)

  def mouseMoveEvent(self, event):
    super(Slider, self).mouseMoveEvent(event)
    val = self.pixelPosToRangeValue(event.pos())
    self.setValue(val)

  def pixelPosToRangeValue(self, pos):
    opt = QtWidgets.QStyleOptionSlider()
    self.initStyleOption(opt)
    gr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self)
    sr = self.style().subControlRect(QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderHandle, self)

    if self.orientation() == QtCore.Qt.Horizontal:
      sliderLength = sr.width()
      sliderMin = gr.x()
      sliderMax = gr.right() - sliderLength + 1
    else:
      sliderLength = sr.height()
      sliderMin = gr.y()
      sliderMax = gr.bottom() - sliderLength + 1;
    pr = pos - sr.center() + sr.topLeft()
    p = pr.x() if self.orientation() == QtCore.Qt.Horizontal else pr.y()
    return QtWidgets.QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), p - sliderMin, sliderMax - sliderMin, opt.upsideDown)
