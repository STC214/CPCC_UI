import sys
import os
import logging
import builtins  # 添加builtins模块导入
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QProgressBar, QTextEdit, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QDateTime
from PyQt5.QtGui import QIcon, QColor, QPalette, QFont, QTextCursor
import cleaner_module
import old_module
import new_module


class ProcessingWorker(QThread):
    update_log = pyqtSignal(str)
    update_progress = pyqtSignal(int)
    finished = pyqtSignal(bool, str)

    def __init__(self, method_type, working_dir):
        super().__init__()
        self.method_type = method_type  # "new" or "old"
        self.working_dir = working_dir

    def run(self):
        try:
            # 保存原始stdout/stderr
            original_stdout = sys.stdout
            original_stderr = sys.stderr

            # 重定向标准输出
            class OutputRedirector:
                def __init__(self, signal):
                    self.signal = signal

                def write(self, text):
                    if text.strip():  # 忽略空行
                        self.signal.emit(text)

                def flush(self):
                    pass

            sys.stdout = OutputRedirector(self.update_log)
            sys.stderr = OutputRedirector(self.update_log)

            # 设置工作目录
            os.chdir(self.working_dir)
            self.update_log.emit(f"设置工作目录: {self.working_dir}")

            # 第一步：执行cleaner
            self.update_log.emit("\n" + "=" * 50)
            self.update_log.emit("开始执行清理操作...")
            self.update_log.emit("=" * 50)
            self.update_progress.emit(10)
            cleaner_module.main()

            # 第二步：执行选择的方法
            if self.method_type == "new":
                self.update_log.emit("\n" + "=" * 50)
                self.update_log.emit("开始使用新方法处理文件...")
                self.update_log.emit("=" * 50)
                self.update_progress.emit(40)

                # 为new_module提供自动确认 - 完全覆盖input函数
                original_input = builtins.input

                def auto_input(prompt=""):
                    """在GUI模式下自动确认所有输入请求"""
                    # 自动确认所有提示
                    response = "y"
                    self.update_log.emit(f"\n[GUI自动确认] {prompt} ➜ '{response}'")
                    return response

                # 安全地覆盖内置input函数
                builtins.input = auto_input

                try:
                    new_module.main()
                finally:
                    # 确保恢复原始input函数
                    builtins.input = original_input
            else:  # 旧方法
                self.update_log.emit("\n" + "=" * 50)
                self.update_log.emit("开始使用旧方法处理文件...")
                self.update_log.emit("=" * 50)
                self.update_progress.emit(40)
                old_module.main()

            self.update_progress.emit(100)
            self.finished.emit(True, "✅ 处理成功完成！")
        except Exception as e:
            import traceback
            error_msg = f"❌ 处理过程中发生错误:\n{str(e)}\n\n{traceback.format_exc()}"
            self.update_log.emit(error_msg)
            self.finished.emit(False, error_msg)
        finally:
            # 恢复标准输出
            sys.stdout = original_stdout
            sys.stderr = original_stderr


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("漫画文件处理工具")

        # 设置窗口图标
        icon_path = self.get_resource_path("04.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 设置Darcula主题
        self.setup_dark_theme()

        # 获取工作目录
        self.working_dir = self.get_working_directory()

        # 设置中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(15, 15, 15, 15)
        layout.setSpacing(10)

        # 标题区域
        title_label = QLabel("漫画文件处理工具")
        title_label.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("color: #A9B7C6; margin: 5px 0;")
        layout.addWidget(title_label)

        # 工作目录显示
        dir_frame = QWidget()
        dir_frame.setStyleSheet("""
            QWidget {
                background-color: #3C3F41;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        dir_layout = QVBoxLayout(dir_frame)
        dir_label = QLabel("当前工作目录:")
        dir_label.setStyleSheet("color: #808080; font-size: 10pt;")
        self.dir_path_label = QLabel(self.working_dir)
        self.dir_path_label.setStyleSheet("color: #6897BB; font-weight: bold;")
        self.dir_path_label.setWordWrap(True)
        dir_layout.addWidget(dir_label)
        dir_layout.addWidget(self.dir_path_label)
        layout.addWidget(dir_frame)

        # 按钮区域
        button_widget = QWidget()
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(20)
        self.new_method_btn = QPushButton("新方法")
        self.old_method_btn = QPushButton("旧方法")

        # 设置按钮样式
        button_style = """
            QPushButton {
                background-color: #3C5A7C;
                color: #A9B7C6;
                border: 1px solid #313335;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #4C6A8C;
            }
            QPushButton:pressed {
                background-color: #214283;
            }
            QPushButton:disabled {
                background-color: #3C3F41;
                color: #666666;
                border: 1px solid #4B4B4B;
            }
        """
        self.new_method_btn.setStyleSheet(button_style)
        self.old_method_btn.setStyleSheet(button_style)
        self.new_method_btn.clicked.connect(lambda: self.start_processing("new"))
        self.old_method_btn.clicked.connect(lambda: self.start_processing("old"))
        button_layout.addStretch()
        button_layout.addWidget(self.new_method_btn)
        button_layout.addWidget(self.old_method_btn)
        button_layout.addStretch()
        layout.addWidget(button_widget)

        # 进度条
        progress_widget = QWidget()
        progress_layout = QVBoxLayout(progress_widget)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_label = QLabel("处理进度:")
        progress_label.setStyleSheet("color: #808080; font-size: 10pt;")
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #313335;
                border-radius: 4px;
                text-align: center;
                color: #A9B7C6;
                background-color: #3C3F41;
                height: 25px;
            }
            QProgressBar::chunk {
                background-color: #6897BB;
                border-radius: 3px;
            }
        """)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(progress_label)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_widget)

        # 日志区域
        log_label = QLabel("处理日志:")
        log_label.setStyleSheet("color: #808080; font-size: 10pt;")
        layout.addWidget(log_label)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setFont(QFont("Consolas", 10))
        self.log_area.setStyleSheet("""
            QTextEdit {
                background-color: #2B2B2B;
                color: #A9B7C6;
                border: 1px solid #313335;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self.log_area, 1)  # 比例1，允许扩展

        # 状态栏
        self.status_bar = self.statusBar()
        self.status_bar.setStyleSheet("""
            QStatusBar {
                background-color: #3C3F41;
                color: #A9B7C6;
                border-top: 1px solid #313335;
            }
        """)
        self.status_bar.showMessage("就绪")

        # 工作线程
        self.worker = None

        # 初始化日志
        self.init_log()

    def get_resource_path(self, relative_path):
        """获取资源的绝对路径，适用于打包后的应用"""
        try:
            # PyInstaller创建的临时文件夹路径
            base_path = sys._MEIPASS
        except Exception:
            # 正常执行时的路径
            base_path = os.path.abspath(".")
        return os.path.join(base_path, relative_path)

    def get_working_directory(self):
        """获取正确的当前工作目录"""
        if getattr(sys, 'frozen', False):
            # 打包后的应用
            return os.path.dirname(sys.executable)
        else:
            # 开发环境
            return os.path.dirname(os.path.abspath(__file__))

    def setup_dark_theme(self):
        """设置Darcula主题"""
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(43, 43, 43))          # #2B2B2B
        palette.setColor(QPalette.WindowText, QColor(169, 183, 198))   # #A9B7C6
        palette.setColor(QPalette.Base, QColor(43, 43, 43))            # #2B2B2B
        palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))   # #353535
        palette.setColor(QPalette.ToolTipBase, QColor(169, 183, 198))  # #A9B7C6
        palette.setColor(QPalette.ToolTipText, QColor(169, 183, 198))  # #A9B7C6
        palette.setColor(QPalette.Text, QColor(169, 183, 198))         # #A9B7C6
        palette.setColor(QPalette.Button, QColor(60, 90, 124))         # #3C5A7C
        palette.setColor(QPalette.ButtonText, QColor(169, 183, 198))   # #A9B7C6
        palette.setColor(QPalette.BrightText, QColor(255, 255, 255))   # #FFFFFF
        palette.setColor(QPalette.Highlight, QColor(33, 66, 131))      # #214283
        palette.setColor(QPalette.HighlightedText, QColor(169, 183, 198))  # #A9B7C6
        self.setPalette(palette)

    def init_log(self):
        """初始化日志区域"""
        self.add_log("欢迎使用漫画文件处理工具\n")
        self.add_log(f"工作目录: {self.working_dir}\n")
        self.add_log("请从上方选择处理方法:\n")
        self.add_log("- 新方法: cleaner.py → new.py (自动确认所有提示)\n")
        self.add_log("- 旧方法: cleaner.py → old.py\n")

    def add_log(self, text):
        """添加日志文本"""
        cursor = self.log_area.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.log_area.setTextCursor(cursor)

        # 为特定文本添加颜色
        if text.startswith("✅"):
            self.log_area.setTextColor(QColor(84, 160, 96))  # 成功绿色
        elif text.startswith("❌"):
            self.log_area.setTextColor(QColor(204, 85, 85))  # 错误红色
        elif "=" * 20 in text:
            self.log_area.setTextColor(QColor(104, 151, 187))  # 进度蓝色
        else:
            self.log_area.setTextColor(QColor(169, 183, 198))  # 默认文字色

        self.log_area.insertPlainText(text)
        self.log_area.ensureCursorVisible()

        # 恢复默认颜色
        self.log_area.setTextColor(QColor(169, 183, 198))

    def start_processing(self, method_type):
        """开始处理文件"""
        # 确认操作
        method_name = "新方法" if method_type == "new" else "旧方法"
        reply = QMessageBox.question(
            self,
            "确认操作",
            f"确定要使用{method_name}处理当前目录中的文件吗?\n\n"
            "此操作可能会修改或删除文件，请确保已备份重要数据。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )

        if reply != QMessageBox.Yes:
            return

        # 禁用按钮防止重复点击
        self.new_method_btn.setEnabled(False)
        self.old_method_btn.setEnabled(False)
        self.progress_bar.setValue(0)

        # 清除之前的日志，保留初始信息
        self.log_area.clear()
        self.init_log()

        self.add_log(f"\n{'=' * 60}")
        self.add_log(f"开始使用{method_name}处理文件")
        self.add_log(f"时间: {QDateTime.currentDateTime().toString('yyyy-MM-dd hh:mm:ss')}")
        self.add_log(f"{'=' * 60}\n")

        # 更新状态
        self.status_bar.showMessage(f"正在使用{method_name}处理文件...")

        # 创建并启动工作线程
        self.worker = ProcessingWorker(method_type, self.working_dir)
        self.worker.update_log.connect(self.add_log)
        self.worker.update_progress.connect(self.progress_bar.setValue)
        self.worker.finished.connect(self.processing_finished)
        self.worker.start()

    def processing_finished(self, success, message):
        """处理完成后的回调"""
        self.new_method_btn.setEnabled(True)
        self.old_method_btn.setEnabled(True)

        self.add_log("\n" + "=" * 60)
        self.add_log(message)
        self.add_log("=" * 60 + "\n")

        if success:
            self.status_bar.showMessage("处理完成! 请检查结果。", 5000)
            QMessageBox.information(
                self,
                "处理完成",
                "文件处理已成功完成!\n请检查目录中的结果文件。"
            )
        else:
            self.status_bar.showMessage("处理失败! 请检查日志。", 5000)
            QMessageBox.critical(
                self,
                "处理失败",
                "文件处理过程中发生错误!\n请检查下方日志获取详细信息。"
            )


def main():
    app = QApplication(sys.argv)

    # 设置应用样式和字体
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 9))

    # 创建并显示主窗口
    window = MainWindow()
    window.setMinimumSize(800, 600)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()