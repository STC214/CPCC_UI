import os
import sys
import logging
import shutil
import zipfile
import re
from pathlib import Path
from PIL import Image
from typing import Set

# ====================== 配置常量 ======================
IMAGE_EXTS = ('.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff')
SKIP_DIRS = {'$RECYCLE.BIN', 'System Volume Information', '.DS_Store'}
START_NUM = 9000
COMPRESS_LEVEL = zipfile.ZIP_STORED

# ====================== 日志配置 ======================
def get_root() -> Path:
    """获取正确的根目录路径"""
    # 在模块中，我们期望工作目录已由主程序设置
    return Path(os.getcwd())

logger = logging.getLogger(__name__)

# ====================== 进度管理 ======================
class ProgressManager:
    def __init__(self, total_steps=9):
        self.total_steps = total_steps
        self.current_step = 0
        self.total_progress = 0.0
        self.task_progress = 0.0
        print("\n" * 3)  # 为进度条预留空间
        self._update_display()

    def step_start(self, step_name: str):
        self.current_step += 1
        self.task_progress = 0.0
        logger.info(f"STEP {self.current_step}: {step_name}")
        self._update_display()

    def update_task(self, progress: float):
        self.task_progress = max(0.0, min(1.0, progress))
        self._update_display()

    def _update_display(self):
        sys.stdout.write("\033[3A")  # 上移三行
        sys.stdout.write(f"总进度: {self._create_bar((self.current_step-1 + self.task_progress)/self.total_steps)}\n")
        sys.stdout.write(f"当前任务: {self._create_bar(self.task_progress)}\n")
        sys.stdout.write("\n")  # 占位行
        sys.stdout.flush()

    @staticmethod
    def _create_bar(progress: float, width: int = 30) -> str:
        filled = int(progress * width)
        return f"[{'█'*filled}{' '*(width-filled)}] {progress*100:.1f}%"

# ====================== 工具函数 ======================
def natural_sort_key(path: Path) -> list:
    """自然排序键函数"""
    return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', path.name)]

def safe_rename(src: Path, dst: Path) -> bool:
    """安全的重命名函数"""
    try:
        if src == dst:
            return True
        
        if dst.exists():
            # 生成唯一文件名
            counter = 1
            while True:
                new_name = f"{dst.stem}_{counter}{dst.suffix}"
                new_dst = dst.parent / new_name
                if not new_dst.exists():
                    dst = new_dst
                    break
                counter += 1
        
        src.rename(dst)
        return True
    except Exception as e:
        logger.error(f"重命名失败 {src} -> {dst}: {e}")
        return False

# ====================== 核心步骤实现 ======================
def step1_convert(root: Path, progress: ProgressManager):
    """步骤1：转换非JPG图像到JPG格式"""
    convert_list = []
    for path in root.rglob('*'):
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS:
            if path.suffix.lower() not in ('.jpg', '.jpeg'):
                convert_list.append(path)
    
    total = len(convert_list)
    for idx, file in enumerate(convert_list):
        try:
            with Image.open(file) as img:
                rgb_img = img.convert('RGB')
                new_path = file.with_suffix('.jpg')
                rgb_img.save(new_path, quality=95, optimize=True)
                file.unlink()
                logger.info(f"Converted {file} to {new_path}")
        except Exception as e:
            logger.error(f"Failed to convert {file}: {e}")
        progress.update_task((idx+1)/total)

def step2_rename(root: Path, progress: ProgressManager):
    """步骤2：四位数字重命名（解决冲突问题）"""
    def process_subdir(subdir: Path):
        files = sorted([f for f in subdir.iterdir() if f.is_file() and f.suffix.lower() == '.jpg'], key=natural_sort_key)
        used_numbers = set()
        for idx, file in enumerate(files):
            new_num = START_NUM + idx
            while f"{new_num:04d}" in used_numbers:
                new_num += 1
            new_name = f"{new_num:04d}.jpg"
            new_path = subdir / new_name
            if safe_rename(file, new_path):
                used_numbers.add(f"{new_num:04d}")
                logger.info(f"Renamed {file} to {new_path}")

    subdirs = [d for d in root.glob('*/*') if d.is_dir() and d.parent.parent == root]
    total = len(subdirs)
    for idx, subdir in enumerate(subdirs):
        process_subdir(subdir)
        progress.update_task((idx+1)/total)

def step3_rename_subdirs(root: Path, progress: ProgressManager):
    """步骤3：重命名次级子目录为四位数字"""
    def process_parent(parent: Path):
        subdirs = sorted([d for d in parent.iterdir() if d.is_dir()], key=natural_sort_key)
        used_numbers = set()
        for idx, subdir in enumerate(subdirs):
            new_num = START_NUM + idx
            while f"{new_num:04d}" in used_numbers:
                new_num += 1
            new_name = f"{new_num:04d}"
            new_path = parent / new_name
            if safe_rename(subdir, new_path):
                used_numbers.add(new_name)
                logger.info(f"Renamed directory {subdir} to {new_path}")

    parent_dirs = [d for d in root.iterdir() if d.is_dir()]
    total = len(parent_dirs)
    for idx, parent in enumerate(parent_dirs):
        process_parent(parent)
        progress.update_task((idx+1)/total)

def step4_add_prefix(root: Path, progress: ProgressManager):
    """步骤4：添加目录名前缀"""
    def process_subdir(subdir: Path):
        dir_num = subdir.name
        for file in subdir.glob('*.jpg'):
            new_name = f"{dir_num}_{file.name}"
            new_path = file.parent / new_name
            if safe_rename(file, new_path):
                logger.info(f"Added prefix {file} -> {new_path}")

    subdirs = [d for d in root.rglob('*') if d.is_dir() and d.parent.parent == root]
    total = len(subdirs)
    for idx, subdir in enumerate(subdirs):
        process_subdir(subdir)
        progress.update_task((idx+1)/total)

def step5_move_files(root: Path, progress: ProgressManager):
    """步骤5：移动文件到父目录"""
    def process_subdir(subdir: Path):
        parent = subdir.parent
        for file in subdir.glob('*.jpg'):
            try:
                base_name = file.name
                new_path = parent / base_name
                counter = 1
                while new_path.exists():
                    new_name = f"{file.stem}_{counter}{file.suffix}"
                    new_path = parent / new_name
                    counter += 1
                shutil.move(str(file), str(new_path))
                logger.info(f"Moved {file} to {new_path}")
            except Exception as e:
                logger.error(f"Failed to move {file}: {e}")

    subdirs = [d for d in root.rglob('*') if d.is_dir() and d.parent.parent == root]
    total = len(subdirs)
    for idx, subdir in enumerate(subdirs):
        process_subdir(subdir)
        progress.update_task((idx+1)/total)

def step6_clean_dirs(root: Path, progress: ProgressManager):
    """步骤6：删除空目录"""
    dirs = list(root.rglob('*'))
    total = len(dirs)
    for idx, path in enumerate(reversed(dirs)):
        if path.is_dir() and not any(path.iterdir()):
            try:
                path.rmdir()
                logger.info(f"Removed empty directory: {path}")
            except Exception as e:
                logger.error(f"Failed to remove {path}: {e}")
        progress.update_task((idx+1)/total)

def step7_final_rename(root: Path, progress: ProgressManager):
    """步骤7：最终四位数字重命名（从0001开始）"""
    def process_dir(directory: Path):
        files = sorted([f for f in directory.glob('*.jpg')], key=natural_sort_key)
        
        # 临时重命名阶段
        temp_files = []
        for idx, file in enumerate(files):
            temp_name = f"temp_{idx:04d}.jpg"
            temp_path = directory / temp_name
            try:
                file.rename(temp_path)
                temp_files.append(temp_path)
            except Exception as e:
                logger.error(f"临时重命名失败 {file}: {e}")
        
        # 最终重命名阶段
        for idx, temp_path in enumerate(temp_files, start=1):
            target_name = f"{idx:04d}.jpg"
            target_path = directory / target_name
            try:
                temp_path.rename(target_path)
                logger.info(f"重命名为 {target_path}")
            except Exception as e:
                logger.error(f"最终重命名失败 {temp_path}: {e}")

    dirs = [d for d in root.iterdir() if d.is_dir()]
    total = len(dirs)
    for idx, d in enumerate(dirs):
        process_dir(d)
        progress.update_task((idx+1)/total)

def step8_compress(root: Path, progress: ProgressManager):
    """步骤8：压缩子目录"""
    def compress_dir(src: Path):
        zip_file = src.with_suffix('.zip')
        with zipfile.ZipFile(zip_file, 'w', COMPRESS_LEVEL) as zf:
            for file in src.rglob('*'):
                if file.is_file():
                    zf.write(file, arcname=file.relative_to(src))
        try:
            shutil.rmtree(src)
            logger.info(f"Compressed {src} to {zip_file}")
        except Exception as e:
            logger.error(f"Failed to remove {src}: {e}")

    dirs = [d for d in root.iterdir() if d.is_dir()]
    total = len(dirs)
    for idx, d in enumerate(dirs):
        compress_dir(d)
        progress.update_task((idx+1)/total)

def step9_rename_cbz(root: Path, progress: ProgressManager):
    """步骤9：重命名ZIP为CBZ"""
    zip_files = list(root.glob('*.zip'))
    total = len(zip_files)
    for idx, zip_file in enumerate(zip_files):
        cbz_file = zip_file.with_suffix('.cbz')
        try:
            zip_file.rename(cbz_file)
            logger.info(f"Renamed {zip_file} to {cbz_file}")
        except Exception as e:
            logger.error(f"Failed to rename {zip_file}: {e}")
        progress.update_task((idx+1)/total)

# ====================== 主程序 ======================
def main():
    """主函数，执行处理流程"""
    root_dir = get_root()
    print(f"根目录: {root_dir.resolve()}")

    # 配置日志
    logging.basicConfig(
        filename='conversion.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filemode='w'
    )

    # Windows控制台支持
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.kernel32.SetConsoleMode(windll.kernel32.GetStdHandle(-11), 7)
        except Exception as e:
            logger.warning(f"设置Windows控制台模式失败: {e}")

    progress = ProgressManager()

    try:
        progress.step_start("转换非JPG图像")
        step1_convert(root_dir, progress)
        
        progress.step_start("四位数字重命名")
        step2_rename(root_dir, progress)
        
        progress.step_start("重命名次级目录")
        step3_rename_subdirs(root_dir, progress)
        
        progress.step_start("添加目录名前缀")
        step4_add_prefix(root_dir, progress)
        
        progress.step_start("移动文件到父目录")
        step5_move_files(root_dir, progress)
        
        progress.step_start("清理空目录")
        step6_clean_dirs(root_dir, progress)
        
        progress.step_start("最终文件重命名")
        step7_final_rename(root_dir, progress)
        
        progress.step_start("压缩子目录")
        step8_compress(root_dir, progress)
        
        progress.step_start("重命名ZIP为CBZ")
        step9_rename_cbz(root_dir, progress)

        print("\n处理完成！")
    except Exception as e:
        logger.critical(f"程序崩溃: {str(e)}", exc_info=True)
        print(f"\n致命错误: {str(e)}")