from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QLineEdit
)

class KafkaBrokerBar(QWidget):
    """Shared broker / topic bar reused in reader and writer panels."""

    def __init__(self, show_group=False):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        lbl_b = QLabel("Broker")
        lbl_b.setObjectName("lbl_key")
        self.inp_broker = QLineEdit()
        self.inp_broker.setPlaceholderText("broker:9092")

        lbl_t = QLabel("Topic")
        lbl_t.setObjectName("lbl_key")
        self.inp_topic = QLineEdit()
        self.inp_topic.setPlaceholderText("topic-name")

        row.addWidget(lbl_b)
        row.addWidget(self.inp_broker, 2)
        row.addWidget(lbl_t)
        row.addWidget(self.inp_topic, 2)

        if show_group:
            lbl_g = QLabel("Consumer Group")
            lbl_g.setObjectName("lbl_key")
            self.inp_group = QLineEdit()
            self.inp_group.setPlaceholderText("kafkapt-consumer")
            row.addWidget(lbl_g)
            row.addWidget(self.inp_group, 2)