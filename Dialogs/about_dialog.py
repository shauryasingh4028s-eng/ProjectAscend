from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)


class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("About Project Ascend")
        self.setFixedSize(420, 320)

        self.setStyleSheet("""
            QDialog{
                background:#111318;
                color:white;
                font-family:Segoe UI;
            }

            QLabel{
                border:none;
            }

            QPushButton{
                background:#2f6fed;
                color:white;
                border:none;
                border-radius:8px;
                padding:10px;
                font-weight:bold;
            }

            QPushButton:hover{
                background:#3d7cff;
            }
        """)

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(12)

        logo = QLabel("🚀")
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("font-size:56px;")

        title = QLabel("Project Ascend")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "font-size:26px;font-weight:bold;"
        )

        version = QLabel("Version 1.0.0")
        version.setAlignment(Qt.AlignCenter)

        author = QLabel("Created by Shaurya Singh")
        author.setAlignment(Qt.AlignCenter)

        copyright_label = QLabel("© 2026 Project Ascend")
        copyright_label.setAlignment(Qt.AlignCenter)

        close_button = QPushButton("Close")
        close_button.clicked.connect(self.accept)

        layout.addWidget(logo)
        layout.addWidget(title)
        layout.addWidget(version)
        layout.addWidget(author)
        layout.addWidget(copyright_label)
        layout.addStretch()
        layout.addWidget(close_button)

        self.setLayout(layout)