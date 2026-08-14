from PySide6.QtCore import QTimer, QTime


class LiveClock:
    def __init__(self, label):
        self.label = label

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)

        self.update_time()

    def update_time(self):
        current_time = QTime.currentTime().toString("hh:mm:ss AP")
        self.label.setText(current_time)