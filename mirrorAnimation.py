import os
import pymel.core as pm

from maya import OpenMayaUI as omui

try:
    from PySide2.QtCore import *
    from PySide2.QtGui import *
    from PySide2.QtWidgets import *
    from PySide2 import __version__
    from shiboken2 import wrapInstance
except ImportError:
    from PySide.QtCore import *
    from PySide.QtGui import *
    from PySide import __version__
    from shiboken import wrapInstance

# TODO

# Get the Maya window so we can parent our widget to it.
mayaMainWindowPtr = omui.MQtUtil.mainWindow()
mayaMainWindow = wrapInstance(long(mayaMainWindowPtr), QWidget)


def xformMirror(transforms=[], across='YZ', behaviour=True):
    """ Mirrors transform across hyperplane.

    transforms -- list of Transform or string.
    across -- plane which to mirror across.
    behaviour -- bool

    """

    # No specified transforms, so will get selection
    if not transforms:
        transforms = pm.selected(type='transform')

    # Check to see all provided objects is an instance of pymel transform node,
    elif not all(map(lambda x: isinstance(x, pm.nt.Transform), transforms)):
        raise ValueError("Passed node which wasn't of type: Transform")

    # Validate plane which to mirror across,
    if not across in ('XY', 'YZ', 'XZ'):
        raise ValueError("Keyword Argument: 'across' not of accepted value ('XY', 'YZ', 'XZ').")

    for transform in transforms:

        # Get the worldspace matrix, as a list of 16 float values
        mtx = pm.xform(transform, q=True, ws=True, m=True)

        # Invert rotation columns,
        rx = [n * -1 for n in mtx[0:9:4]]
        ry = [n * -1 for n in mtx[1:10:4]]
        rz = [n * -1 for n in mtx[2:11:4]]

        # Invert translation row,
        t = [n * -1 for n in mtx[12:15]]

        # Set matrix based on given plane, and whether to include behaviour or not.
        if across is 'XY':
            mtx[14] = t[2]  # set inverse of the Z translation

            # Set inverse of all rotation columns but for the one we've set translate to.
            if behaviour:
                mtx[0:9:4] = rx
                mtx[1:10:4] = ry

        elif across is 'YZ':
            mtx[12] = t[0]  # set inverse of the X translation

            if behaviour:
                mtx[1:10:4] = ry
                mtx[2:11:4] = rz
        else:
            mtx[13] = t[1]  # set inverse of the Y translation

            if behaviour:
                mtx[0:9:4] = rx
                mtx[2:11:4] = rz


def mirrorMatrix(mtx, plane):
    """ """
    if not isinstance(mtx, pm.dt.Matrix):
        raise ValueError("mtx must be a PyMel Matrix")

    if not isinstance(plane, str):
        raise ValueError("Plane must be of type (str)")

    if plane.upper() in ('X', 'Y', 'Z'):
        raise ValueError("Plane must be either of X, Y or Z")

    pass


class Window(QWidget):

    def __init__(self, parent=mayaMainWindow):
        super(Window, self).__init__(parent=parent)

        if os.name is 'posix':
            self.setWindowFlags(Qt.Tool)
        else:
            self.setWindowFlags(Qt.Window)

        self.setWindowTitle("Mirror Animation Tool")

        # Integer for jobnumber of scripjob we're going to create,
        self.jobNumber = None

        layout = QGridLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(1)

        # Set column width to 100%
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

        self.table.verticalHeader().setVisible(False)

        sel = pm.selected()
        self.table.setHorizontalHeaderItem(
            0,
            QTableWidgetItem(sel[0].nodeName() if sel else "Driver")
        )

        layout.addWidget(self.table, 0, 0, 1, 2, Qt.AlignHCenter)

        offsetLayout = QHBoxLayout()
        self.offset = QLineEdit()
        self.offset.setValidator(QDoubleValidator())
        self.setDefaultOffset()

        offsetLayout.addWidget(QLabel("Mirror Offset:"))
        offsetLayout.addWidget(self.offset)

        layout.addLayout(offsetLayout, 1, 0, 1, 2, Qt.AlignHCenter)

        btnLayout = QHBoxLayout()
        # Mirror Button
        self.mirrorBtn = QPushButton("Mirror")
        self.mirrorBtn.clicked.connect(self.mirror)

        # Invert Curves
        self.invertBtn = QPushButton("Invert")
        self.invertBtn.clicked.connect(self.invert)

        btnLayout.addWidget(self.mirrorBtn)
        btnLayout.addWidget(self.invertBtn)

        layout.addLayout(btnLayout, 2, 0, 1, 2, Qt.AlignHCenter)

        self.setLayout(layout)

    def setDefaultOffset(self):
        """ Assume half the timerange is to be equal to desired offset time,"""
        minTime = pm.playbackOptions(query=True, minTime=True)
        maxTime = pm.playbackOptions(query=True, maxTime=True)
        self.offset.insert(
            str((maxTime - minTime) / 2)
        )

    def animatedAttributes(self, node):
        """ Return a list of tuples pairs for all animated attributes,
        with AnimationCurve and nice name,

        """
        # attributes = [(attr, attr.split('_')[-1]) for attr in pm.keyframe(node, attribute=pm.listAttr(node, keyable=True), query=True, name=True)]
        attributes = list()
        animationCurves = pm.keyframe(
            node,
            query=True,
            name=True,
            attribute=pm.listAttr(node, keyable=True)
        )

        for curve in animationCurves:
            attributes.append(
                (curve, curve.split('_')[-1])
            )

        return attributes

    def populateColumn(self, column, header, attributes):
        """ """
        headerItem = QTableWidgetItem(header)
        self.table.setHorizontalHeaderItem(column, headerItem)

        for row, attribute in enumerate(attributes):

            # Unpack attribute,
            animCurve, attrName = attribute

            attributeItem = AnimationCurveItem(animCurve, attrName)
            attributeItem.setFlags(attributeItem.flags() ^ Qt.ItemIsEditable)
            self.table.setItem(row, column, attributeItem)

    def callback(self):
        """ """
        sel = pm.selected()

        if sel:

            # Set column header to first selection,
            header = sel[0].nodeName()

            # Get all animated attributes,
            attributes = self.animatedAttributes(sel[0])

            self.table.setRowCount(len(attributes))

            self.populateColumn(0, header, attributes)

        else:
            self.table.setHorizontalHeaderItem(0, QTableWidgetItem("Driver"))
            self.table.setRowCount(0)

    def createScriptJob(self):
        """ Maya script job, run callback whenever selection changes, """
        jobNumber = pm.scriptJob(event=('SelectionChanged', self.callback))
        return jobNumber

    def mirror(self):
        """ Copy the animation curves from first to second selection item, """
        sel = pm.selected()

        if len(sel) == 2:

            pm.copyKey(
                sel[0]
            )

            pm.pasteKey(
                sel[1],
                timeOffset=float(self.offset.text()),
                option='replace',
            )

    def invert(self):
        """ Invert animation curves for current selection, """
        items = self.table.selectedItems()
        for item in items:
            self.invertCurve(item.animationCurve)

    def showEvent(self, e):
        """ On show create a Maya scripjob unless one already exists for some reason,"""
        if self.jobNumber and pm.scriptJob(exists=self.jobNumber):
            # ScriptJob already seem to exist, so let's do nothing
            pass
        else:
            self.createScriptJob()

    def closeEvent(self, e):
        """ Remove scriptjob, """
        if self.jobNumber and pm.scriptJob(exists=self.jobNumber):
            pm.scriptJob(kill=self.jobNumber)
            self.jobNumber = None

    def offsetCurve(self, animationCurve, offset):
        """ Move the animation curve relative in time to offset, """
        pm.keyframe(
            animationCurve,
            edit=True,
            includeUpperBound=True,
            relative=True,
            option='over',
            timeChange=offset,
        )

    def invertCurve(self, animationCurve):
        """ Scale the values by negative one, """
        pm.scaleKey(
            animationCurve,
            valueScale=-1,
            valuePivot=0,
        )

    def getAnimcurveLength(self, animationCurve):
        """ Get the duration for animation curve,
        max key - min key,
        """

        keys = pm.keyframe(
            animationCurve,
            query=True,
            timeChange=True
        )

        return keys[-1] - keys[0]

    def getKeysInCurve(self, animationCurve):
        """ Get a list of tuple pairs (key, value) in animationCurve, """
        data = pm.keyframe(
            animationCurve,
            query=True,
            valueChange=True,
            timeChange=True,
        )
        return data

class AnimationCurveItem(QTableWidgetItem):
    """ Subclassing Table Item to store reference to animation curves, """
    def __init__(self, animationCurve, *args, **kwargs):
        super(AnimationCurveItem, self).__init__(*args, **kwargs)
        self.animationCurve = animationCurve

def ui():
    window = Window()
    window.show()
    return window