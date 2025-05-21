import os
import random
import subprocess
import shlex

# --- 配置 ---
AUDIO_FILES_DIR = "audio_files"  # 修改：指定音频文件夹
VIDEO_MATERIALS_DIR = "video_materials"
TEMP_FILE_LIST = "temp_filelist.txt"
TEMP_CONCATENATED_VIDEO = "temp_concatenated_video.mp4"
# --- End Configuration ---

def get_media_duration(file_path):
    """使用 ffprobe 获取媒体文件的时长（秒）"""
    command = f"ffprobe -v error -show_entries format=duration -of default=noprint_wrappers=1:nokey=1 {shlex.quote(file_path)}"
    try:
        process = subprocess.Popen(shlex.split(command), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output, error = process.communicate(timeout=30)
        if process.returncode == 0 and output:
            return float(output.strip())
        else:
            print(f"获取时长错误 for {file_path}: {error or 'ffprobe returned no output'}")
            return None
    except subprocess.TimeoutExpired:
        print(f"获取时长超时 for {file_path}")
        process.kill()
        return None
    except Exception as e:
        print(f"执行 ffprobe 时发生未知错误 for {file_path}: {e}")
        return None

def process_single_audio(audio_file_path, video_files_with_durations):
    """处理单个音频文件并生成对应视频"""
    print(f"\n--- 开始处理音频文件: {audio_file_path} ---")
    
    # 根据当前音频文件名确定输出视频文件名
    base_name = os.path.basename(audio_file_path)
    name_without_ext = os.path.splitext(base_name)[0]
    output_video_filename = name_without_ext + ".mp4"
    output_video_path = os.path.join(os.getcwd(), output_video_filename) # 保存在脚本运行的当前目录

    target_audio_duration = get_media_duration(audio_file_path)
    if target_audio_duration is None:
        print(f"无法获取音频文件 {audio_file_path} 的时长。跳过此文件。")
        return

    print(f"音频时长: {target_audio_duration:.2f} 秒 for {audio_file_path}")

    if not video_files_with_durations:
        print("视频素材列表为空。无法处理。") # 此情况应在 main 中被捕获，但再次检查
        return

    total_video_material_duration = sum(v['duration'] for v in video_files_with_durations)
    # print(f"总可用视频素材时长: {total_video_material_duration:.2f} 秒") # 此信息可在 main 中打印一次

    if total_video_material_duration < target_audio_duration:
        print(f"警告: 所有视频素材的总时长 ({total_video_material_duration:.2f}s) 短于目标音频时长 ({target_audio_duration:.2f}s) for {audio_file_path}。")
        print("脚本将使用所有可用素材，但最终视频可能短于音频。")

    selected_videos_for_concat = []
    current_concatenated_duration = 0.0
    
    available_videos = list(video_files_with_durations) # 创建副本
    random.shuffle(available_videos)
    video_pool_for_selection = list(available_videos)

    print(f"开始为 {audio_file_path} 随机选择视频素材...")
    while current_concatenated_duration < target_audio_duration:
        if not video_pool_for_selection:
            print(f"视频池已用尽 for {audio_file_path}，重新填充以允许重复使用视频...")
            video_pool_for_selection = list(available_videos) # 重新填充
            if not video_pool_for_selection:
                 print(f"没有可用的视频素材了 for {audio_file_path}。")
                 break

        selected_video = random.choice(video_pool_for_selection)
        selected_videos_for_concat.append(selected_video['path'])
        current_concatenated_duration += selected_video['duration']
        print(f"  已选择: {selected_video['path']} (时长: {selected_video['duration']:.2f}s). 当前总时长: {current_concatenated_duration:.2f}s")

    if not selected_videos_for_concat:
        print(f"没有选择任何视频进行拼接 for {audio_file_path}。跳过此文件。")
        return

    print(f"视频选择完成 for {audio_file_path}。总共选择了 {len(selected_videos_for_concat)} 个片段。")
    print(f"预计拼接后视频时长: {current_concatenated_duration:.2f} 秒")

    with open(TEMP_FILE_LIST, 'w', encoding='utf-8') as f:
        for video_path_item in selected_videos_for_concat:
            f.write(f"file '{os.path.abspath(video_path_item)}'\n")
    
    print(f"临时文件列表已创建: {TEMP_FILE_LIST} for {audio_file_path}")

    concat_command = (
        f"ffmpeg -y -f concat -safe 0 -i {shlex.quote(TEMP_FILE_LIST)} "
        f"-c copy {shlex.quote(TEMP_CONCATENATED_VIDEO)}"
    )
    print(f"执行拼接命令 for {audio_file_path}: {concat_command}")
    try:
        process_concat = subprocess.run(shlex.split(concat_command), check=True, capture_output=True, text=True, timeout=300)
        print(f"视频拼接成功 for {audio_file_path}.")
        # print(process_concat.stdout) # 可以取消注释以查看ffmpeg输出
    except subprocess.CalledProcessError as e:
        print(f"视频拼接失败 for {audio_file_path}。返回码: {e.returncode}")
        print(f"错误信息: {e.stderr}")
        if os.path.exists(TEMP_FILE_LIST): os.remove(TEMP_FILE_LIST)
        return # 跳到下一个音频文件
    except subprocess.TimeoutExpired:
        print(f"视频拼接超时 for {audio_file_path}.")
        if os.path.exists(TEMP_FILE_LIST): os.remove(TEMP_FILE_LIST)
        return
    except Exception as e:
        print(f"视频拼接时发生未知错误 for {audio_file_path}: {e}")
        if os.path.exists(TEMP_FILE_LIST): os.remove(TEMP_FILE_LIST)
        return

    merge_command = (
        f"ffmpeg -y -i {shlex.quote(TEMP_CONCATENATED_VIDEO)} -i {shlex.quote(audio_file_path)} "
        f"-c:v copy -c:a aac -map 0:v:0 -map 1:a:0 -shortest "
        f"{shlex.quote(output_video_path)}"
    )
    print(f"执行合并命令 for {audio_file_path}: {merge_command}")
    try:
        process_merge = subprocess.run(shlex.split(merge_command), check=True, capture_output=True, text=True, timeout=300)
        print(f"视频和音频合并成功 for {audio_file_path}! 输出文件: {output_video_path}")
        # print(process_merge.stdout)
    except subprocess.CalledProcessError as e:
        print(f"视频和音频合并失败 for {audio_file_path}。返回码: {e.returncode}")
        print(f"错误信息: {e.stderr}")
    except subprocess.TimeoutExpired:
        print(f"视频和音频合并超时 for {audio_file_path}.")
    except Exception as e:
        print(f"视频和音频合并时发生未知错误 for {audio_file_path}: {e}")
    finally:
        if os.path.exists(TEMP_FILE_LIST):
            os.remove(TEMP_FILE_LIST)
            print(f"已删除临时文件: {TEMP_FILE_LIST}")
        if os.path.exists(TEMP_CONCATENATED_VIDEO):
            os.remove(TEMP_CONCATENATED_VIDEO)
            print(f"已删除临时文件: {TEMP_CONCATENATED_VIDEO}")
    print(f"--- 完成处理音频文件: {audio_file_path} ---")


def main():
    if not os.path.isdir(AUDIO_FILES_DIR):
        print(f"错误: 音频文件夹 {AUDIO_FILES_DIR} 不存在。请检查路径。")
        return
    if not os.path.isdir(VIDEO_MATERIALS_DIR):
        print(f"错误: 视频素材文件夹 {VIDEO_MATERIALS_DIR} 不存在。请检查路径。")
        return

    print(f"扫描视频素材文件夹: {VIDEO_MATERIALS_DIR}")
    video_files_with_durations = []
    for item in os.listdir(VIDEO_MATERIALS_DIR):
        if item.lower().endswith(('.mp4', '.mov', '.avi', '.mkv')):
            video_path = os.path.join(VIDEO_MATERIALS_DIR, item)
            duration = get_media_duration(video_path)
            if duration and duration > 0:
                video_files_with_durations.append({"path": video_path, "duration": duration})
            else:
                print(f"跳过视频 {video_path} 因为无法获取有效时长或时长为0。")

    if not video_files_with_durations:
        print("视频素材文件夹中没有找到有效的视频文件。脚本终止。")
        return
    
    print(f"总共找到 {len(video_files_with_durations)} 个有效视频素材。")
    total_video_material_duration = sum(v['duration'] for v in video_files_with_durations)
    print(f"总可用视频素材时长: {total_video_material_duration:.2f} 秒。")


    audio_files_to_process = []
    print(f"扫描音频文件夹: {AUDIO_FILES_DIR}")
    for item in os.listdir(AUDIO_FILES_DIR):
        # 支持常见的音频格式
        if item.lower().endswith(('.mp3', '.wav', '.aac', '.m4a', '.flac', '.ogg')):
            audio_files_to_process.append(os.path.join(AUDIO_FILES_DIR, item))

    if not audio_files_to_process:
        print(f"在文件夹 {AUDIO_FILES_DIR} 中没有找到支持的音频文件。脚本终止。")
        return
    
    print(f"找到 {len(audio_files_to_process)} 个音频文件待处理: {audio_files_to_process}")

    for audio_path in audio_files_to_process:
        process_single_audio(audio_path, video_files_with_durations)
    
    print("\n所有音频文件处理完毕。")

if __name__ == "__main__":
    main() 