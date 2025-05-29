import os
import subprocess
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog, QProgressBar, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

class FFmpegThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str) # success, message
    file_processed_signal = pyqtSignal(str) # filename

    def __init__(self, video_folder, audio_folder, silent_video_folder, parent=None):
        super().__init__(parent)
        self.video_folder = video_folder
        self.audio_folder = audio_folder
        self.silent_video_folder = silent_video_folder
        self.is_running = True

    def run_ffmpeg_command(self, command_list, operation_description):
        self.progress_signal.emit(f"执行 FFmpeg: {operation_description}...")
        try:
            # CREATE_NO_WINDOW is for Windows to hide the console
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
            stdout, stderr = process.communicate() # Wait for command to complete

            if not self.is_running: # Check if thread was stopped prematurely
                 self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 被中止。")
                 if process.poll() is None: # if process is still running
                    process.terminate()
                    process.wait()
                 return False

            if process.returncode == 0:
                self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 成功。")
                # if stdout: self.progress_signal.emit(f"FFmpeg STDOUT:\n{stdout.strip()}")
                return True
            else:
                self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 失败 (返回码 {process.returncode}).")
                # if stdout: self.progress_signal.emit(f"FFmpeg STDOUT:\n{stdout.strip()}")
                if stderr: self.progress_signal.emit(f"FFmpeg STDERR:\n{stderr.strip()}")
                return False
        except FileNotFoundError:
            self.progress_signal.emit("FFmpeg 命令未找到。请确保 FFmpeg 已安装并已添加到系统 PATH。")
            return False
        except Exception as e:
            self.progress_signal.emit(f"执行 FFmpeg 命令时发生 Python 错误: {e}")
            return False

    def run(self):
        self.is_running = True
        self.progress_signal.emit(f"视频文件夹: {self.video_folder}")
        self.progress_signal.emit(f"音频输出文件夹: {self.audio_folder}")
        self.progress_signal.emit(f"无声视频输出文件夹: {self.silent_video_folder}")
        
        supported_video_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm')

        if not os.path.isdir(self.video_folder):
            self.finished_signal.emit(False, f"错误：视频文件夹 '{self.video_folder}' 不存在。")
            return

        for folder_path, description in [(self.audio_folder, "音频输出"), (self.silent_video_folder, "无声视频输出")]:
            if not os.path.exists(folder_path):
                try:
                    os.makedirs(folder_path)
                    self.progress_signal.emit(f"已创建{description}文件夹：'{folder_path}'")
                except OSError as e:
                    self.finished_signal.emit(False, f"错误：无法创建{description}文件夹 '{folder_path}': {e}")
                    return
        
        self.progress_signal.emit(f"开始处理文件夹 '{self.video_folder}' 中的视频...")
        total_files_to_process = sum(1 for f in os.listdir(self.video_folder) if os.path.isfile(os.path.join(self.video_folder, f)) and f.lower().endswith(supported_video_extensions))
        processed_files_count = 0
        successfully_processed_files = 0

        if total_files_to_process == 0:
            self.finished_signal.emit(True, "在指定文件夹中没有找到支持的视频文件。")
            return

        for filename in os.listdir(self.video_folder):
            if not self.is_running:
                self.progress_signal.emit("处理被用户中止。")
                break
            
            video_file_path = os.path.join(self.video_folder, filename)

            if os.path.isfile(video_file_path) and filename.lower().endswith(supported_video_extensions):
                self.progress_signal.emit(f"\n正在处理视频文件: {filename} ({processed_files_count + 1}/{total_files_to_process})")
                base_name, _ = os.path.splitext(filename)
                
                audio_op_success = False
                video_op_success = False

                # 1. 提取音频
                audio_filename = base_name + ".mp3"
                audio_file_path = os.path.join(self.audio_folder, audio_filename)
                command_audio = ['ffmpeg', '-i', video_file_path, '-vn', '-acodec', 'libmp3lame', '-y', audio_file_path]
                if self.run_ffmpeg_command(command_audio, f"提取音频从 {filename}"):
                     self.progress_signal.emit(f"成功提取音频到: {audio_file_path}")
                     audio_op_success = True
                else:
                    self.progress_signal.emit(f"提取音频文件 '{filename}' 失败。")
                
                if not self.is_running: break

                # 2. 创建无声视频副本
                silent_video_file_full_path = os.path.join(self.silent_video_folder, filename)
                command_silent_video = ['ffmpeg', '-i', video_file_path, '-an', '-vcodec', 'copy', '-y', silent_video_file_full_path]
                
                if self.run_ffmpeg_command(command_silent_video, f"创建无声视频 (vcodec copy) {filename}"):
                    self.progress_signal.emit(f"成功保存无声视频到: {silent_video_file_full_path}")
                    video_op_success = True
                else:
                    self.progress_signal.emit(f"使用 -vcodec copy 创建无声视频 '{filename}' 失败。尝试使用 libx264 重新编码...")
                    command_silent_video_recode = ['ffmpeg', '-i', video_file_path, '-an', '-vcodec', 'libx264', '-preset', 'fast', '-y', silent_video_file_full_path]
                    if self.run_ffmpeg_command(command_silent_video_recode, f"创建无声视频 (libx264) {filename}"):
                        self.progress_signal.emit(f"成功使用 libx264 重新编码并保存无声视频到: {silent_video_file_full_path}")
                        video_op_success = True
                    else:
                        self.progress_signal.emit(f"使用 libx264 为 '{filename}' 重新编码无声视频也失败了。")
                
                processed_files_count += 1
                if audio_op_success or video_op_success: # Count as success if at least one op is successful
                    successfully_processed_files +=1
                self.file_processed_signal.emit(filename)

            elif os.path.isfile(video_file_path):
                self.progress_signal.emit(f"跳过非视频文件: {filename}")
        
        if self.is_running:
            if successfully_processed_files > 0:
                 self.finished_signal.emit(True, f"处理完成。共成功处理 {successfully_processed_files}/{total_files_to_process} 个视频文件。")
            elif total_files_to_process > 0 :
                self.finished_signal.emit(False, "处理完成，但没有文件成功处理。请检查日志。")
            # else: (case of no video files was handled earlier)

    def stop(self):
        self.is_running = False
        self.progress_signal.emit("正在尝试中止处理...")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频音频处理工具 (FFmpeg + PyQt6)")
        self.setGeometry(100, 100, 700, 550) # x, y, width, height

        self.ffmpeg_thread = None

        # --- Main Widget and Layout ---
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Path Selection --- 
        path_layout_labels = ["视频文件夹路径:", "音频输出路径:", "无声视频输出路径:"]
        self.path_entries = []

        for i, label_text in enumerate(path_layout_labels):
            h_layout = QHBoxLayout()
            label = QLabel(label_text)
            entry = QLineEdit()
            entry.setPlaceholderText(f"选择{label_text.split(':')[0]}")
            button = QPushButton("浏览")
            button.clicked.connect(lambda checked, e=entry: self.browse_folder(e))
            
            h_layout.addWidget(label)
            h_layout.addWidget(entry)
            h_layout.addWidget(button)
            main_layout.addLayout(h_layout)
            self.path_entries.append(entry)

        # --- Status Text Box ---
        self.status_textbox = QTextEdit()
        self.status_textbox.setReadOnly(True)
        main_layout.addWidget(self.status_textbox, 1) # Stretch factor

        # --- Progress Bar ---
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        # --- Buttons Layout ---
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.start_processing)
        self.stop_button = QPushButton("中止处理")
        self.stop_button.clicked.connect(self.stop_processing)
        self.stop_button.setEnabled(False)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        main_layout.addLayout(button_layout)
        
        self.log_message("请确保您的系统已正确安装 FFmpeg 并将其添加到了系统 PATH。")
        self.log_message("如果处理卡住或出错，请检查 FFmpeg 是否能从命令行正常运行。")

    def browse_folder(self, entry_widget):
        folder_selected = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder_selected:
            entry_widget.setText(folder_selected)

    def log_message(self, message):
        self.status_textbox.append(message)
        # self.status_textbox.ensureCursorVisible() # Alternative to scrolling
        self.status_textbox.verticalScrollBar().setValue(self.status_textbox.verticalScrollBar().maximum()) 


    def start_processing(self):
        video_folder = self.path_entries[0].text()
        audio_folder = self.path_entries[1].text()
        silent_video_folder = self.path_entries[2].text()

        if not all([video_folder, audio_folder, silent_video_folder]):
            QMessageBox.warning(self, "路径不完整", "所有三个路径都必须填写！")
            return

        self.status_textbox.clear()
        self.log_message("开始处理...")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(0) # Indeterminate at first

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.ffmpeg_thread = FFmpegThread(video_folder, audio_folder, silent_video_folder)
        self.ffmpeg_thread.progress_signal.connect(self.log_message)
        self.ffmpeg_thread.finished_signal.connect(self.processing_finished)
        self.ffmpeg_thread.file_processed_signal.connect(self.update_progress_bar)
        self.ffmpeg_thread.start()

    def stop_processing(self):
        if self.ffmpeg_thread and self.ffmpeg_thread.isRunning():
            self.log_message("发送中止信号...")
            self.ffmpeg_thread.stop()
            # UI update for finished state will be handled by finished_signal
            self.stop_button.setEnabled(False) # Prevent multiple clicks
            
    def update_progress_bar(self, filename_processed): # filename is just for potential future use
        # Update progress bar based on number of files processed
        if self.ffmpeg_thread:
            current_max = self.progress_bar.maximum()
            if current_max == 0: # If it was indeterminate, set the max now
                # Count files to process (could be done once at start of thread too)
                video_folder = self.path_entries[0].text()
                supported_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.flv', '.wmv', '.webm')
                try:
                    total_files = sum(1 for f in os.listdir(video_folder) if os.path.isfile(os.path.join(video_folder, f)) and f.lower().endswith(supported_extensions))
                    self.progress_bar.setMaximum(total_files if total_files > 0 else 100) # Avoid max 0
                except FileNotFoundError:
                    self.progress_bar.setMaximum(100) # Default if folder not found
            
            self.progress_bar.setValue(self.progress_bar.value() + 1)

    def processing_finished(self, success, message):
        self.log_message(message)
        if success:
            QMessageBox.information(self, "处理完成", message)
        else:
            QMessageBox.warning(self, "处理出错或中止", message)
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.progress_bar.setValue(self.progress_bar.maximum()) # Fill bar on finish or set to 0 if preferred
        self.ffmpeg_thread = None # Clear the thread reference
        
    def closeEvent(self, event):
        # Ensure FFmpeg thread is stopped if window is closed
        if self.ffmpeg_thread and self.ffmpeg_thread.isRunning():
            self.log_message("窗口关闭，正在中止处理...")
            self.ffmpeg_thread.stop()
            self.ffmpeg_thread.wait() # Wait for thread to actually finish
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec()) 