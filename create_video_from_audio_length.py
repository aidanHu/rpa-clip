import os
import random
import subprocess
import shlex
import sys
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QPushButton, QLabel, QLineEdit, QTextEdit, QFileDialog, QProgressBar, QMessageBox
)
from PyQt6.QtCore import QThread, pyqtSignal, Qt

# --- 配置 ---
TEMP_FILE_LIST = "temp_filelist.txt"
TEMP_CONCATENATED_VIDEO = "temp_concatenated_video.mp4"
# --- End Configuration ---

class VideoCreationThread(QThread):
    progress_signal = pyqtSignal(str)            # For general log messages
    file_progress_signal = pyqtSignal(int, int)  # current_file_index, total_files
    finished_signal = pyqtSignal(bool, str)      # success (bool), final_message (str)

    def __init__(self, audio_dir, video_material_dir, output_dir, parent=None):
        super().__init__(parent)
        self.audio_dir = audio_dir
        self.video_material_dir = video_material_dir
        self.output_dir = output_dir
        self.is_running = True

    def _get_media_duration(self, file_path):
        command = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path]
        self.progress_signal.emit(f"获取文件时长: {os.path.basename(file_path)}...")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
            output, error = process.communicate(timeout=30)
            if process.returncode == 0 and output:
                return float(output.strip())
            else:
                self.progress_signal.emit(f"获取时长错误 for {os.path.basename(file_path)}: {error or 'ffprobe returned no output'}")
                return None
        except subprocess.TimeoutExpired:
            self.progress_signal.emit(f"获取时长超时 for {os.path.basename(file_path)}")
            if process.poll() is None: process.kill()
            return None
        except Exception as e:
            self.progress_signal.emit(f"执行 ffprobe 时发生未知错误 for {os.path.basename(file_path)}: {e}")
            return None

    def _run_ffmpeg_command(self, command_list, operation_description):
        self.progress_signal.emit(f"执行 FFmpeg: {operation_description}...")
        try:
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            process = subprocess.Popen(command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=creationflags)
            stdout, stderr = process.communicate() # Wait for command to complete

            if not self.is_running: # Check if thread was stopped
                 self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 被中止。")
                 if process.poll() is None: process.terminate(); process.wait()
                 return False

            if process.returncode == 0:
                self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 成功。")
                return True
            else:
                self.progress_signal.emit(f"FFmpeg 操作 '{operation_description}' 失败 (返回码 {process.returncode}).")
                if stderr: self.progress_signal.emit(f"FFmpeg STDERR:\n{stderr.strip()}")
                return False
        except FileNotFoundError:
            self.progress_signal.emit("FFmpeg/ffprobe 命令未找到。请确保已安装并添加到系统 PATH。")
            return False # Critical error, stop further processing for this file or all?
        except Exception as e:
            self.progress_signal.emit(f"执行 FFmpeg/ffprobe 命令时发生 Python 错误: {e}")
            return False

    def run(self):
        self.is_running = True
        self.progress_signal.emit(f"开始处理...")
        self.progress_signal.emit(f"音频文件夹: {self.audio_dir}")
        self.progress_signal.emit(f"视频素材文件夹: {self.video_material_dir}")
        self.progress_signal.emit(f"输出文件夹: {self.output_dir}")

        # 1. 扫描视频素材并获取时长
        self.progress_signal.emit("扫描视频素材...")
        video_files_with_durations = []
        try:
            for item in os.listdir(self.video_material_dir):
                if not self.is_running: break
                if item.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
                    video_path = os.path.join(self.video_material_dir, item)
                    duration = self._get_media_duration(video_path)
                    if duration and duration > 0:
                        video_files_with_durations.append({"path": video_path, "duration": duration})
                    else:
                        self.progress_signal.emit(f"跳过视频素材 {item} 因为无法获取有效时长或时长为0。")
        except FileNotFoundError:
            self.finished_signal.emit(False, f"错误：视频素材文件夹 '{self.video_material_dir}' 未找到。")
            return
        except Exception as e:
            self.finished_signal.emit(False, f"扫描视频素材时出错: {e}")
            return
            
        if not self.is_running: self.finished_signal.emit(False, "处理被用户中止。" ); return

        if not video_files_with_durations:
            self.finished_signal.emit(False, "视频素材文件夹中没有找到有效的视频文件。")
            return
        self.progress_signal.emit(f"总共找到 {len(video_files_with_durations)} 个有效视频素材。")
        total_video_material_duration = sum(v['duration'] for v in video_files_with_durations)
        self.progress_signal.emit(f"总可用视频素材时长: {total_video_material_duration:.2f} 秒。")

        # 2. 扫描音频文件
        audio_files_to_process = []
        try:
            for item in os.listdir(self.audio_dir):
                if not self.is_running: break
                if item.lower().endswith(('.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg')):
                    audio_files_to_process.append(os.path.join(self.audio_dir, item))
        except FileNotFoundError:
            self.finished_signal.emit(False, f"错误：音频文件夹 '{self.audio_dir}' 未找到。")
            return
        except Exception as e:
            self.finished_signal.emit(False, f"扫描音频文件时出错: {e}")
            return

        if not self.is_running: self.finished_signal.emit(False, "处理被用户中止。"); return

        if not audio_files_to_process:
            self.finished_signal.emit(False, f"在文件夹 {self.audio_dir} 中没有找到支持的音频文件。")
            return
        self.progress_signal.emit(f"找到 {len(audio_files_to_process)} 个音频文件待处理.")

        # 3. 处理每个音频文件
        successful_creations = 0
        for idx, audio_file_path in enumerate(audio_files_to_process):
            if not self.is_running: break
            self.file_progress_signal.emit(idx, len(audio_files_to_process))
            self.progress_signal.emit(f"\n--- 开始处理音频文件: {os.path.basename(audio_file_path)} ({idx+1}/{len(audio_files_to_process)}) ---")

            target_audio_duration = self._get_media_duration(audio_file_path)
            if target_audio_duration is None:
                self.progress_signal.emit(f"无法获取音频 {os.path.basename(audio_file_path)} 的时长。跳过此文件。")
                continue
            self.progress_signal.emit(f"音频时长: {target_audio_duration:.2f} 秒 for {os.path.basename(audio_file_path)}")

            if total_video_material_duration < target_audio_duration:
                self.progress_signal.emit(f"警告: 所有视频素材总时长 ({total_video_material_duration:.2f}s) 短于目标音频 ({target_audio_duration:.2f}s)。视频将使用所有素材但可能短于音频。")

            selected_videos_for_concat = []
            current_concatenated_duration = 0.0
            available_videos_copy = list(video_files_with_durations)
            random.shuffle(available_videos_copy)
            video_pool = list(available_videos_copy)

            while current_concatenated_duration < target_audio_duration and self.is_running:
                if not video_pool:
                    self.progress_signal.emit(f"视频池已用尽 for {os.path.basename(audio_file_path)}，重新填充...")
                    video_pool = list(available_videos_copy) # Re-populate
                    if not video_pool: self.progress_signal.emit("无法重新填充视频池，素材不足。"); break 
                
                selected_video = random.choice(video_pool)
                selected_videos_for_concat.append(selected_video['path'])
                current_concatenated_duration += selected_video['duration']
            
            if not self.is_running: break
            if not selected_videos_for_concat:
                self.progress_signal.emit(f"没有选择任何视频进行拼接 for {os.path.basename(audio_file_path)}。跳过。")
                continue
            
            self.progress_signal.emit(f"为 {os.path.basename(audio_file_path)} 选择了 {len(selected_videos_for_concat)} 个片段，预计总时长 {current_concatenated_duration:.2f}s.")

            # 使用绝对路径写入文件列表，以提高 ffmpeg -safe 0 的可靠性
            abs_temp_file_list = os.path.abspath(TEMP_FILE_LIST)
            with open(abs_temp_file_list, 'w', encoding='utf-8') as f:
                for video_path_item in selected_videos_for_concat:
                    # 1. 获取绝对路径
                    abs_video_path = os.path.abspath(video_path_item)
                    # 2. 将反斜杠替换为正斜杠
                    normalized_path = abs_video_path.replace("\\", "/")
                    # 3. 构建要写入的行
                    line_to_write = f"file '{normalized_path}'\n"
                    f.write(line_to_write)
            
            abs_temp_concat_video = os.path.abspath(TEMP_CONCATENATED_VIDEO)
            concat_command = ['ffmpeg', '-y', '-f', 'concat', '-safe', '0', '-i', abs_temp_file_list, '-c', 'copy', abs_temp_concat_video]
            if not self._run_ffmpeg_command(concat_command, f"拼接视频 for {os.path.basename(audio_file_path)}"): 
                if os.path.exists(abs_temp_file_list): os.remove(abs_temp_file_list)
                continue # Skip to next audio file
            
            if not self.is_running: break

            output_video_filename = os.path.splitext(os.path.basename(audio_file_path))[0] + ".mp4"
            output_video_path = os.path.join(self.output_dir, output_video_filename)
            
            merge_command = ['ffmpeg', '-y', '-i', abs_temp_concat_video, '-i', audio_file_path, 
                             '-c:v', 'copy', '-c:a', 'aac', '-map', '0:v:0', '-map', '1:a:0', 
                             '-shortest', output_video_path]
            if self._run_ffmpeg_command(merge_command, f"合并音视频 for {os.path.basename(audio_file_path)}"):
                self.progress_signal.emit(f"成功创建视频: {output_video_path}")
                successful_creations += 1
            else:
                self.progress_signal.emit(f"合并音视频失败 for {os.path.basename(audio_file_path)}.")

            # Cleanup temporary files
            if os.path.exists(abs_temp_file_list): os.remove(abs_temp_file_list)
            if os.path.exists(abs_temp_concat_video): os.remove(abs_temp_concat_video)
            self.progress_signal.emit(f"--- 完成处理音频文件: {os.path.basename(audio_file_path)} ---")
        # End of loop for audio files

        if not self.is_running:
            self.finished_signal.emit(False, f"处理被用户中止。最终成功创建 {successful_creations} 个视频。")
            return

        self.file_progress_signal.emit(len(audio_files_to_process), len(audio_files_to_process)) # Final progress update
        self.finished_signal.emit(True, f"所有音频文件处理完毕。成功创建 {successful_creations} 个视频。")

    def stop(self):
        self.is_running = False
        self.progress_signal.emit("正在尝试中止处理...")

class VideoCreatorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("视频按音频长度生成工具 (FFmpeg + PyQt6)")
        self.setGeometry(100, 100, 750, 600)
        self.creation_thread = None

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Path inputs
        self.audio_dir_entry = self._create_path_entry(layout, "音频文件夹路径:")
        self.video_material_dir_entry = self._create_path_entry(layout, "视频素材文件夹路径:")
        self.output_dir_entry = self._create_path_entry(layout, "输出文件夹路径:")

        # Status Text Box
        self.status_textbox = QTextEdit()
        self.status_textbox.setReadOnly(True)
        layout.addWidget(self.status_textbox, 1)

        # Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # Buttons
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.start_creation)
        self.stop_button = QPushButton("中止处理")
        self.stop_button.clicked.connect(self.stop_creation)
        self.stop_button.setEnabled(False)
        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        layout.addLayout(button_layout)

        self.log("请确保系统中已正确安装 FFmpeg 和 ffprobe，并已将其添加到系统 PATH 中。")
        self.log("或者，将 ffmpeg.exe 和 ffprobe.exe 放置在打包后的 .exe 文件同目录下。")

    def _create_path_entry(self, parent_layout, label_text):
        h_layout = QHBoxLayout()
        label = QLabel(label_text)
        entry = QLineEdit()
        entry.setPlaceholderText(f"选择{label_text.split(':')[0]}")
        button = QPushButton("浏览")
        button.clicked.connect(lambda _, e=entry: self._browse_folder(e))
        h_layout.addWidget(label)
        h_layout.addWidget(entry)
        h_layout.addWidget(button)
        parent_layout.addLayout(h_layout)
        return entry

    def _browse_folder(self, entry_widget):
        folder = QFileDialog.getExistingDirectory(self, "选择文件夹")
        if folder:
            entry_widget.setText(folder)

    def log(self, message):
        self.status_textbox.append(message)
        self.status_textbox.verticalScrollBar().setValue(self.status_textbox.verticalScrollBar().maximum())

    def update_progress(self, current_file_idx, total_files):
        if total_files > 0:
            self.progress_bar.setMaximum(total_files)
            self.progress_bar.setValue(current_file_idx)
        else:
            self.progress_bar.setMaximum(100) # Should not happen if checks are in place
            self.progress_bar.setValue(0)

    def start_creation(self):
        audio_dir = self.audio_dir_entry.text()
        video_dir = self.video_material_dir_entry.text()
        out_dir = self.output_dir_entry.text()

        if not all([audio_dir, video_dir, out_dir]):
            QMessageBox.warning(self, "路径不完整", "所有三个路径都必须填写！")
            return
        
        if not os.path.isdir(audio_dir):
            QMessageBox.warning(self, "路径无效", f"音频文件夹路径无效: {audio_dir}")
            return
        if not os.path.isdir(video_dir):
            QMessageBox.warning(self, "路径无效", f"视频素材文件夹路径无效: {video_dir}")
            return
        
        if not os.path.exists(out_dir):
            try:
                os.makedirs(out_dir)
                self.log(f"已创建输出文件夹: {out_dir}")
            except Exception as e:
                QMessageBox.critical(self, "创建文件夹失败", f"无法创建输出文件夹 {out_dir}: {e}")
                return
        elif not os.path.isdir(out_dir):
             QMessageBox.warning(self, "路径无效", f"指定的输出路径是一个文件而不是文件夹: {out_dir}")
             return

        self.status_textbox.clear()
        self.log("开始视频创建过程...")
        self.progress_bar.setValue(0)
        self.progress_bar.setMaximum(0) # Indeterminate until first file progress signal

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)

        self.creation_thread = VideoCreationThread(audio_dir, video_dir, out_dir)
        self.creation_thread.progress_signal.connect(self.log)
        self.creation_thread.file_progress_signal.connect(self.update_progress)
        self.creation_thread.finished_signal.connect(self.creation_finished)
        self.creation_thread.start()

    def stop_creation(self):
        if self.creation_thread and self.creation_thread.isRunning():
            self.log("发送中止信号给视频创建线程...")
            self.creation_thread.stop()
            self.stop_button.setEnabled(False) # Prevent multiple clicks

    def creation_finished(self, success, message):
        self.log(message)
        if success:
            QMessageBox.information(self, "处理完成", message)
        else:
            if "中止" not in message: # Don't show warning if user manually stopped
                 QMessageBox.warning(self, "处理出错或中止", message)
        
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        # Ensure progress bar is full or reset
        if self.progress_bar.maximum() > 0:
            self.progress_bar.setValue(self.progress_bar.maximum() if success else self.progress_bar.value())
        else: # If it was indeterminate or no files
            self.progress_bar.setValue(100 if success else 0)
            self.progress_bar.setMaximum(100)
            
        self.creation_thread = None

    def closeEvent(self, event):
        if self.creation_thread and self.creation_thread.isRunning():
            reply = QMessageBox.question(self, '确认退出',
                                       "处理仍在进行中。确定要退出吗？",
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                       QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.log("窗口关闭，正在中止视频创建...")
                self.creation_thread.stop()
                self.creation_thread.wait() # Wait for thread to finish
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = VideoCreatorWindow()
    window.show()
    sys.exit(app.exec()) 