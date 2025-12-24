import os
import sys
import logging
import shutil
import zipfile
import re
import argparse
import json
import time
from pathlib import Path
from datetime import datetime
from PIL import Image
from typing import Set, List, Dict, Any, Optional, Tuple
import tempfile
import uuid

# ====================== 配置常量 ======================
DEFAULT_CONFIG = {
    "image_exts": ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', '.tiff'],
    "skip_dirs": ['$RECYCLE.BIN', 'System Volume Information', '.DS_Store'],
    "start_num": 0,  # Fixed: Python 3 doesn't allow leading zeros in integers
    "compress_level": zipfile.ZIP_DEFLATED,
    "backup_enabled": False,
    "interactive_mode": True,
    "skip_step_confirmations": False,
    "dry_run": False,
    "max_files_per_dir": 1000,
    "progress_update_freq": 0.01  # 每1%更新一次进度，提高刷新频率
}

# ====================== 工具函数 ======================
def get_root() -> Path:
    """获取正确的根目录路径"""
    # 在模块中，我们期望工作目录已由主程序设置
    return Path(os.getcwd())

def setup_logging(root_dir: Path):
    """配置日志系统"""
    log_dir = root_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"conversion_{timestamp}.log"
    
    # 确保日志文件的父目录存在
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filemode='w',
        encoding='utf-8'
    )
    return logging.getLogger(__name__)

# 定义全局logger
logger = None

def natural_sort_key(path: Path) -> list:
    """自然排序键函数"""
    try:
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', path.name)]
    except Exception:
        # 出错时回退到普通排序
        return [path.name.lower()]

def confirm_operation(message: str, config: "ConfigManager") -> bool:
    """确认操作，根据配置决定是否需要用户确认"""
    # 如果配置为跳过确认或者非交互模式，直接返回True
    if config["dry_run"]:
        logger.info(f"[DRY RUN] 跳过确认: {message}")
        return True
    
    if config["skip_step_confirmations"] or not config["interactive_mode"]:
        logger.info(f"跳过确认: {message}")
        return True
    
    # 带有选项的确认提示
    response = input(f"{message} [Y/n/a]: ").strip().lower()
    
    # 'a' 选项：跳过所有后续确认
    if response == 'a':
        config["skip_step_confirmations"] = True
        config.save_config()  # 保存配置
        print("ⓘ 已启用'跳过所有后续确认'选项。")
        return True
    
    # 空或 'y' 为确认
    return response in ['', 'y']

def safe_rename(src: Path, dst: Path, backup_manager: "BackupManager", config: "ConfigManager") -> bool:
    """安全的重命名函数"""
    if not src.exists():
        logger.error(f"源文件不存在: {src}")
        return False
    
    if config["dry_run"]:
        logger.info(f"[DRY RUN] 将重命名 {src} -> {dst}")
        if backup_manager:
            backup_manager.record_operation("rename", src, dst)
        return True
    
    try:
        if src == dst:
            return True
        
        # 检查目标是否已存在
        final_dst = dst
        counter = 1
        while final_dst.exists():
            new_name = f"{dst.stem}_{counter}{dst.suffix}"
            final_dst = dst.parent / new_name
            counter += 1
            if counter > 100:  # 防止无限循环
                logger.error(f"无法找到唯一文件名: {dst}")
                return False
        
        # 记录操作用于回滚
        if backup_manager:
            backup_manager.record_operation("rename", src, final_dst)
        
        src.rename(final_dst)
        logger.info(f"重命名 {src} -> {final_dst}")
        return True
    except Exception as e:
        logger.error(f"重命名失败 {src} -> {dst}: {e}")
        return False

def print_config_summary(config: "ConfigManager"):
    """打印配置摘要"""
    print("\n" + "="*50)
    print("配置摘要:")
    print(f"- 起始编号: {config['start_num']}")
    print(f"- 压缩级别: {config.get_compress_level_name()}")
    print(f"- 交互模式: {'启用' if config['interactive_mode'] else '禁用'}")
    print(f"- 跳过步骤确认: {'启用' if config['skip_step_confirmations'] else '禁用'}")
    print(f"- 模拟运行: {'启用' if config['dry_run'] else '禁用'}")
    print(f"- 备份: {'启用' if config['backup_enabled'] else '禁用'}")
    print("="*50)

# ====================== 配置管理 ======================
class ConfigManager:
    def __init__(self, config_file: Optional[Path] = None):
        self.config = DEFAULT_CONFIG.copy()
        self.config_file = config_file or get_root() / 'config.json'
        self.load_config()
    
    def load_config(self):
        """从文件加载配置"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                # 只合并已知的配置项，避免未知键
                for key in self.config.keys():
                    if key in loaded_config:
                        self.config[key] = loaded_config[key]
                logger.info(f"配置已从 {self.config_file} 加载")
            except Exception as e:
                logger.warning(f"加载配置失败: {e}，使用默认配置")
    
    def save_config(self):
        """保存配置到文件"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logger.info(f"配置已保存到 {self.config_file}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
    
    def __getitem__(self, key):
        return self.config.get(key)
    
    def __setitem__(self, key, value):
        self.config[key] = value
    
    def edit_interactively(self):
        """交互式地编辑配置"""
        print("\n" + "="*50)
        print("配置编辑模式")
        print("="*50)
        while True:
            print("\n当前配置:")
            print(f"1. 起始编号: {self['start_num']}")
            print(f"2. 压缩级别: {self.get_compress_level_name()}")
            print(f"3. 交互模式: {'启用' if self['interactive_mode'] else '禁用'}")
            print(f"4. 跳过步骤确认: {'启用' if self['skip_step_confirmations'] else '禁用'}")
            print(f"5. 备份功能: {'启用' if self['backup_enabled'] else '禁用'}")
            print(f"6. 模拟运行模式(Dry Run): {'启用' if self['dry_run'] else '禁用'}")
            print("7. 保存配置并返回")
            print("8. 放弃更改并返回")
            
            choice = input("\n请选择要修改的配置项 [1-8]: ").strip()
            
            if choice == '1':
                new_val = input(f"输入新的起始编号 (当前: {self['start_num']}): ").strip()
                if new_val.isdigit():
                    self['start_num'] = int(new_val)
                    print(f"✓ 起始编号已更新为: {self['start_num']}")
                else:
                    print("✗ 无效的输入，请输入数字")
            elif choice == '2':
                print("\n可选压缩级别:")
                print("0: 无压缩 (ZIP_STORED)")
                print("8: 标准压缩 (ZIP_DEFLATED) [推荐]")
                print("12: BZIP2 压缩 (ZIP_BZIP2)")
                print("14: LZMA 压缩 (ZIP_LZMA) - 高压缩率，较慢")
                new_val = input(f"输入压缩级别 (当前: {self.get_compress_level_name()}): ").strip()
                valid_levels = {
                    '0': zipfile.ZIP_STORED,
                    '8': zipfile.ZIP_DEFLATED,
                    '12': zipfile.ZIP_BZIP2,
                    '14': zipfile.ZIP_LZMA
                }
                if new_val in valid_levels:
                    self['compress_level'] = valid_levels[new_val]
                    print(f"✓ 压缩级别已更新为: {self.get_compress_level_name()}")
                else:
                    print("✗ 无效的输入，请输入 0, 8, 12 或 14")
            elif choice == '3':
                new_val = not self['interactive_mode']
                self['interactive_mode'] = new_val
                print(f"✓ 交互模式已{'启用' if new_val else '禁用'}")
            elif choice == '4':
                new_val = not self['skip_step_confirmations']
                self['skip_step_confirmations'] = new_val
                print(f"✓ 步骤确认已{'跳过' if new_val else '启用'}")
            elif choice == '5':
                new_val = not self['backup_enabled']
                self['backup_enabled'] = new_val
                print(f"✓ 备份功能已{'启用' if new_val else '禁用'}")
            elif choice == '6':
                new_val = not self['dry_run']
                self['dry_run'] = new_val
                print(f"✓ 模拟运行模式已{'启用' if new_val else '禁用'}")
            elif choice == '7':
                self.save_config()
                print("✓ 配置已保存")
                return True
            elif choice == '8':
                print("ⓘ 放弃更改，返回主菜单")
                return False
            else:
                print("✗ 无效选项，请选择 1-8")
    
    def get_compress_level_name(self):
        """获取压缩级别的可读名称"""
        levels = {
            zipfile.ZIP_STORED: "无压缩 (ZIP_STORED)",
            zipfile.ZIP_DEFLATED: "标准压缩 (ZIP_DEFLATED)",
            zipfile.ZIP_BZIP2: "BZIP2 压缩 (ZIP_BZIP2)",
            zipfile.ZIP_LZMA: "LZMA 压缩 (ZIP_LZMA)"
        }
        return levels.get(self['compress_level'], f"未知级别 ({self['compress_level']})")

# ====================== 备份管理 ======================
class BackupManager:
    def __init__(self, root_dir: Path, config: ConfigManager):
        self.root_dir = root_dir
        self.backup_dir = root_dir / "backups"
        self.config = config
        self.operation_log = []
    
    def create_backup(self) -> Optional[Path]:
        """创建目录备份"""
        if not self.config["backup_enabled"]:
            logger.info("备份功能已禁用")
            return None
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"backup_{timestamp}"
        print(f"\n正在创建备份到 {backup_path}...")
        logger.info(f"创建备份: {backup_path}")
        
        try:
            self.backup_dir.mkdir(exist_ok=True)
            
            # 使用rsync风格的备份，只复制需要的文件
            total_files = 0
            for src_path in self.root_dir.rglob('*'):
                if any(skip in str(src_path) for skip in self.config["skip_dirs"]):
                    continue
                if src_path.is_file() and src_path.suffix.lower() in self.config["image_exts"]:
                    total_files += 1
            
            processed = 0
            for src_path in self.root_dir.rglob('*'):
                if any(skip in str(src_path) for skip in self.config["skip_dirs"]):
                    continue
                if src_path.is_file() and src_path.suffix.lower() in self.config["image_exts"]:
                    rel_path = src_path.relative_to(self.root_dir)
                    dst_path = backup_path / rel_path
                    dst_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src_path), str(dst_path))
                    processed += 1
                    if processed % 100 == 0:
                        progress = processed / max(total_files, 1)
                        print(f"备份进度: {progress:.1%}", end='\r')
            
            print("\n备份完成!")
            logger.info(f"备份完成: {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"备份失败: {e}")
            print(f"警告: 备份失败 - {e}")
            if self.config["interactive_mode"]:
                confirm = input("备份失败，是否继续处理? [y/N]: ").lower().strip()
                return None if confirm != 'y' else None
            return None
    
    def record_operation(self, operation: str, source: Path, target: Optional[Path] = None):
        """记录操作用于可能的回滚"""
        self.operation_log.append({
            "timestamp": time.time(),
            "operation": operation,
            "source": str(source),
            "target": str(target) if target else None
        })
    
    def rollback(self):
        """回滚操作"""
        print("\n开始回滚操作...")
        logger.info("开始回滚操作")
        
        # 按时间倒序处理
        for op in reversed(self.operation_log):
            try:
                if op["operation"] == "rename":
                    src = Path(op["target"])
                    dst = Path(op["source"])
                    if src.exists() and not dst.exists():
                        src.rename(dst)
                        logger.info(f"回滚重命名: {src} -> {dst}")
                elif op["operation"] == "delete":
                    # 无法完全回滚删除操作，记录警告
                    logger.warning(f"无法回滚删除操作: {op['source']}")
                elif op["operation"] == "move":
                    src = Path(op["target"])
                    dst = Path(op["source"])
                    if src.exists():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(str(src), str(dst))
                        logger.info(f"回滚移动: {src} -> {dst}")
            except Exception as e:
                logger.error(f"回滚操作失败: {e}")
        
        print("回滚完成!")
        logger.info("回滚完成")

# ====================== 验证器 ======================
class DirectoryValidator:
    def __init__(self, root_dir: Path, config: ConfigManager):
        self.root_dir = root_dir
        self.config = config
    
    def validate_structure(self) -> Tuple[bool, List[str]]:
        """验证目录结构是否符合预期"""
        issues = []
        
        # 检查根目录是否存在且可访问
        if not self.root_dir.exists():
            issues.append(f"根目录不存在: {self.root_dir}")
            return False, issues
        
        if not self.root_dir.is_dir():
            issues.append(f"路径不是目录: {self.root_dir}")
            return False, issues
        
        # 检查是否有足够权限
        if not os.access(self.root_dir, os.R_OK):
            issues.append(f"没有足够的读取权限: {self.root_dir}")
        
        if not os.access(self.root_dir, os.W_OK) and not self.config["dry_run"]:
            issues.append(f"没有足够的写入权限: {self.root_dir} (在dry run模式下可忽略)")
        
        # 检查目录结构
        parent_dirs = [d for d in self.root_dir.iterdir() if d.is_dir() and d.name not in self.config["skip_dirs"]]
        
        if not parent_dirs:
            issues.append("未找到任何子目录，无法处理")
            return False, issues
        
        valid_structure = False
        for parent in parent_dirs:
            subdirs = [d for d in parent.iterdir() if d.is_dir() and d.name not in self.config["skip_dirs"]]
            if subdirs:  # 如果有任何父目录包含子目录
                valid_structure = True
                break
        
        if not valid_structure:
            issues.append("目录结构不符合预期。期望的结构: 根目录/父目录/子目录/图片文件")
        
        # 检查是否有可处理的文件
        image_files = []
        for path in self.root_dir.rglob('*'):
            if path.is_file() and path.suffix.lower() in self.config["image_exts"]:
                image_files.append(path)
        
        if not image_files:
            issues.append("未找到可处理的图像文件")
        
        return len(issues) == 0, issues
    
    def validate_disk_space(self, required_mb: int = 1000) -> bool:
        """检查磁盘空间是否足够"""
        try:
            import psutil
            disk_usage = psutil.disk_usage(str(self.root_dir))
            free_mb = disk_usage.free / (1024 * 1024)
            if free_mb < required_mb:
                logger.warning(f"磁盘空间不足: 剩余 {free_mb:.1f}MB，需要至少 {required_mb}MB")
                return False
            return True
        except ImportError:
            logger.warning("无法检查磁盘空间: 未安装psutil库")
            print("提示: 安装psutil库以启用磁盘空间检查 (pip install psutil)")
            return True  # 无法检查时假设空间足够

# ====================== 进度管理 ======================
class ProgressManager:
    def __init__(self, total_steps=9, config: Optional[ConfigManager] = None):
        self.total_steps = total_steps
        self.current_step = 0
        self.total_progress = 0.0
        self.task_progress = 0.0
        self.last_update = 0.0
        self.update_freq = config["progress_update_freq"] if config else 0.01
        self.is_windows = sys.platform.startswith('win')
        self.last_display_time = time.time()
        self.min_update_interval = 0.1  # 最小更新间隔(秒)
        self.max_line_length = 120  # 最大行长度，用于清除残留字符
        self.min_width = 80
        
        # 尝试启用Windows ANSI支持
        if self.is_windows:
            try:
                from ctypes import windll
                kernel32 = windll.kernel32
                kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            except Exception:
                pass
        
        # 初始化显示
        self._initialize_display()
        self._update_display()
    
    def _initialize_display(self):
        """初始化显示区域"""
        # 预留足够的空间用于显示
        display_lines = 5
        sys.stdout.write("\n" * display_lines)
        sys.stdout.flush()
    
    def step_start(self, step_name: str):
        self.current_step += 1
        self.task_progress = 0.0
        self.last_update = 0.0
        self.last_display_time = time.time()
        logger.info(f"STEP {self.current_step}: {step_name}")
        self._update_display()
    
    def update_task(self, progress: float):
        self.task_progress = max(0.0, min(1.0, progress))
        
        # 实时更新：每次调用都尝试更新，但限制最小时间间隔
        current_time = time.time()
        if (current_time - self.last_display_time) >= self.min_update_interval:
            self._update_display()
            self.last_display_time = current_time
    
    def complete_step(self):
        """标记当前步骤完成"""
        self.task_progress = 1.0
        self._update_display()
    
    def _update_display(self):
        try:
            # 优先尝试ANSI显示
            self._update_display_ansi()
        except Exception as e:
            logger.warning(f"ANSI进度显示失败，回退到简单模式: {e}")
            self._update_display_simple()
    
    def _update_display_ansi(self):
        """使用ANSI转义序列更新显示"""
        # 获取终端宽度
        try:
            import shutil
            width = max(shutil.get_terminal_size().columns, self.min_width)
        except Exception:
            width = self.max_line_length
        
        # 上移光标覆盖之前的显示
        sys.stdout.write("\033[5A")  # 上移5行
        
        # 总进度
        total_progress = (self.current_step - 1 + self.task_progress) / self.total_steps
        sys.stdout.write(f"总进度: {self._create_bar(total_progress)}".ljust(width) + "\n")
        
        # 当前任务
        sys.stdout.write(f"任务进度: {self._create_bar(self.task_progress)}".ljust(width) + "\n")
        
        # 当前步骤
        sys.stdout.write(f"执行步骤: {self.current_step}/{self.total_steps}".ljust(width) + "\n")
        
        # 空行
        sys.stdout.write("".ljust(width) + "\n")
        
        # 空行（确保底部有足够空间）
        sys.stdout.write("".ljust(width) + "\n")
        
        sys.stdout.flush()
    
    def _update_display_simple(self):
        """简单文本模式更新显示（无ANSI支持）"""
        try:
            import shutil
            width = max(shutil.get_terminal_size().columns, self.min_width)
        except Exception:
            width = self.max_line_length
        
        total_progress = (self.current_step - 1 + self.task_progress) / self.total_steps
        line = "\r"  # 回到行首
        line += f"总进度: {self._create_bar(total_progress, width=20)} | "
        line += f"步骤: {self.current_step}/{self.total_steps} | "
        line += f"任务: {self._create_bar(self.task_progress, width=15)}"
        
        # 确保覆盖整行
        line = line.ljust(width)
        sys.stdout.write(line)
        sys.stdout.flush()
    
    @staticmethod
    def _create_bar(progress: float, width: int = 30) -> str:
        """创建进度条，使用#字符提高兼容性"""
        filled = int(progress * width)
        # 使用#字符替代█，提高终端兼容性
        bar = '#' * filled + ' ' * (width - filled)
        percent = progress * 100
        return f"[{bar}] {percent:.1f}%"

# ====================== 核心步骤实现 ======================
def step1_convert(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤1：转换非JPG图像到JPG格式"""
    convert_list = []
    for path in root.rglob('*'):
        if any(skip in str(path) for skip in config["skip_dirs"]):
            continue
        if path.is_file() and path.suffix.lower() in config["image_exts"]:
            if path.suffix.lower() not in ('.jpg', '.jpeg'):
                convert_list.append(path)
    
    total = len(convert_list)
    if total == 0:
        logger.info("步骤1：没有需要转换的图像文件")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    logger.info(f"步骤1：找到 {total} 个需要转换的图像文件")
    
    if not confirm_operation(
        f"即将转换 {total} 个非JPG图像到JPG格式，这将删除原始文件。确认继续?",
        config
    ):
        logger.info("步骤1：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, file in enumerate(convert_list):
        try:
            if not config["dry_run"]:
                with Image.open(file) as img:
                    # 跳过动画GIF
                    if file.suffix.lower() == '.gif' and getattr(img, 'is_animated', False):
                        logger.info(f"跳过动画GIF: {file}")
                        continue
                    
                    # 处理透明通道
                    if img.mode in ('RGBA', 'LA', 'P'):
                        background = Image.new('RGB', img.size, (255, 255, 255))
                        if img.mode == 'P':
                            img = img.convert('RGBA')
                        background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
                        rgb_img = background
                    else:
                        rgb_img = img.convert('RGB')
                    
                    new_path = file.with_suffix('.jpg')
                    rgb_img.save(new_path, quality=95, optimize=True)
                    
                    backup_manager.record_operation("delete", file)
                    file.unlink()
                    logger.info(f"转换 {file} 为 {new_path}")
            else:
                logger.info(f"[DRY RUN] 将转换 {file} 为 JPG")
        except Exception as e:
            logger.error(f"转换失败 {file}: {e}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step2_rename(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤2：四位数字重命名（解决冲突问题）"""
    def process_subdir(subdir: Path):
        files = sorted([
            f for f in subdir.iterdir()
            if f.is_file() and f.suffix.lower() == '.jpg'
        ], key=natural_sort_key)
        
        used_numbers = set()
        start_num = config["start_num"]
        
        for idx, file in enumerate(files):
            new_num = start_num + idx
            while f"{new_num:04d}" in used_numbers:
                new_num += 1
            
            if new_num >= start_num + 10000:  # 防止四位数溢出
                logger.error(f"目录 {subdir} 中文件数量过多，超过编号范围")
                break
            
            new_name = f"{new_num:04d}.jpg"
            new_path = subdir / new_name
            
            safe_rename(file, new_path, backup_manager, config)
            used_numbers.add(f"{new_num:04d}")
    
    # 获取符合预期结构的子目录
    subdirs = []
    for parent in root.iterdir():
        if parent.is_dir() and parent.name not in config["skip_dirs"]:
            for subdir in parent.iterdir():
                if subdir.is_dir() and subdir.name not in config["skip_dirs"]:
                    subdirs.append(subdir)
    
    total = len(subdirs)
    logger.info(f"步骤2：处理 {total} 个子目录")
    
    if total == 0:
        logger.warning("步骤2：未找到符合结构的子目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将重命名 {total} 个子目录中的文件为四位数字格式。确认继续?",
        config
    ):
        logger.info("步骤2：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, subdir in enumerate(subdirs):
        process_subdir(subdir)
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step3_rename_subdirs(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤3：重命名次级子目录为四位数字"""
    def process_parent(parent: Path):
        subdirs = sorted([
            d for d in parent.iterdir()
            if d.is_dir() and d.name not in config["skip_dirs"]
        ], key=natural_sort_key)
        
        used_numbers = set()
        start_num = config["start_num"]
        
        for idx, subdir in enumerate(subdirs):
            new_num = start_num + idx
            while f"{new_num:04d}" in used_numbers:
                new_num += 1
            
            if new_num >= start_num + 10000:  # 防止四位数溢出
                logger.error(f"父目录 {parent} 中子目录数量过多，超过编号范围")
                break
            
            new_name = f"{new_num:04d}"
            new_path = parent / new_name
            
            safe_rename(subdir, new_path, backup_manager, config)
            used_numbers.add(new_name)
    
    parent_dirs = [
        d for d in root.iterdir()
        if d.is_dir() and d.name not in config["skip_dirs"]
    ]
    
    total = len(parent_dirs)
    logger.info(f"步骤3：处理 {total} 个父目录")
    
    if total == 0:
        logger.warning("步骤3：未找到父目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将重命名 {total} 个父目录下的子目录为四位数字格式。确认继续?",
        config
    ):
        logger.info("步骤3：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, parent in enumerate(parent_dirs):
        process_parent(parent)
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step4_add_prefix(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤4：添加目录名前缀"""
    subdirs = []
    for parent in root.iterdir():
        if parent.is_dir() and parent.name not in config["skip_dirs"]:
            for subdir in parent.iterdir():
                if subdir.is_dir() and subdir.name not in config["skip_dirs"]:
                    subdirs.append(subdir)
    
    total = len(subdirs)
    logger.info(f"步骤4：处理 {total} 个子目录")
    
    if total == 0:
        logger.warning("步骤4：未找到符合结构的子目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将为 {total} 个子目录中的文件添加目录名前缀。确认继续?",
        config
    ):
        logger.info("步骤4：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, subdir in enumerate(subdirs):
        dir_num = subdir.name
        files = sorted([
            f for f in subdir.glob('*.jpg')
            if f.is_file()
        ], key=natural_sort_key)
        
        for file in files:
            if '_' in file.name:  # 跳过已有前缀的文件
                continue
            
            new_name = f"{dir_num}_{file.name}"
            new_path = file.parent / new_name
            
            safe_rename(file, new_path, backup_manager, config)
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step5_move_files(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤5：移动文件到父目录"""
    subdirs = []
    for parent in root.iterdir():
        if parent.is_dir() and parent.name not in config["skip_dirs"]:
            for subdir in parent.iterdir():
                if subdir.is_dir() and subdir.name not in config["skip_dirs"]:
                    subdirs.append((subdir, parent))  # (子目录, 父目录)
    
    total = len(subdirs)
    logger.info(f"步骤5：处理 {total} 个子目录")
    
    if total == 0:
        logger.warning("步骤5：未找到符合结构的子目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将移动 {total} 个子目录中的文件到对应的父目录。确认继续?",
        config
    ):
        logger.info("步骤5：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, (subdir, parent_dir) in enumerate(subdirs):
        files = sorted([
            f for f in subdir.glob('*.jpg')
            if f.is_file()
        ], key=natural_sort_key)
        
        for file in files:
            try:
                base_name = file.name
                new_path = parent_dir / base_name
                counter = 1
                
                # 处理文件名冲突
                while new_path.exists() and counter <= 100:
                    new_name = f"{file.stem}_{counter}{file.suffix}"
                    new_path = parent_dir / new_name
                    counter += 1
                
                if counter > 100:
                    logger.error(f"无法解决文件名冲突: {file}")
                    continue
                
                if not config["dry_run"]:
                    shutil.move(str(file), str(new_path))
                    
                    # 记录操作
                    backup_manager.record_operation("move", file, new_path)
                    logger.info(f"移动 {file} 到 {new_path}")
            except Exception as e:
                logger.error(f"移动失败 {file}: {e}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step6_clean_dirs(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤6：删除空目录"""
    dirs = []
    for path in root.rglob('*'):
        if path.is_dir() and path.name not in config["skip_dirs"]:
            dirs.append(path)
    
    # 逆序处理，确保先处理子目录
    dirs = sorted(dirs, key=lambda x: len(str(x)), reverse=True)
    
    total = len(dirs)
    logger.info(f"步骤6：检查 {total} 个目录是否为空")
    
    if total == 0:
        logger.warning("步骤6：未找到需要清理的目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        "即将清理所有空目录。确认继续?",
        config
    ):
        logger.info("步骤6：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    removed_count = 0
    for idx, path in enumerate(dirs):
        try:
            if not any(path.iterdir()):  # 目录为空
                if not config["dry_run"]:
                    path.rmdir()
                    backup_manager.record_operation("delete", path)
                    logger.info(f"移除空目录: {path}")
                    removed_count += 1
        except Exception as e:
            logger.error(f"移除目录失败 {path}: {e}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    logger.info(f"步骤6：共移除 {removed_count} 个空目录")
    progress.complete_step()  # 确保步骤完成时进度为100%

def step7_final_rename(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤7：最终四位数字重命名（从0001开始）"""
    # 获取所有父目录
    parent_dirs = [
        d for d in root.iterdir()
        if d.is_dir() and d.name not in config["skip_dirs"]
    ]
    
    total = len(parent_dirs)
    logger.info(f"步骤7：处理 {total} 个父目录")
    
    if total == 0:
        logger.warning("步骤7：未找到父目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将对 {total} 个父目录中的文件执行最终重命名(0001开始)。确认继续?",
        config
    ):
        logger.info("步骤7：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, directory in enumerate(parent_dirs):
        # 使用临时目录进行重命名
        with tempfile.TemporaryDirectory(dir=str(directory.parent)) as temp_dir:
            temp_path = Path(temp_dir)
            files = sorted([
                f for f in directory.glob('*.jpg')
                if f.is_file()
            ], key=natural_sort_key)
            
            # 阶段1：移动到临时目录
            temp_files = []
            for file in files:
                if config["dry_run"]:
                    temp_files.append((file.name, file))
                    continue
                
                temp_file = temp_path / file.name
                try:
                    shutil.move(str(file), str(temp_file))
                    temp_files.append((file.name, temp_file))
                    backup_manager.record_operation("move", file, temp_file)
                except Exception as e:
                    logger.error(f"移动到临时目录失败 {file}: {e}")
            
            # 阶段2：从临时目录移回并重命名
            for new_idx, (orig_name, temp_file) in enumerate(temp_files, start=1):
                new_name = f"{new_idx:04d}.jpg"
                new_path = directory / new_name
                
                if config["dry_run"]:
                    logger.info(f"[DRY RUN] 将重命名 {orig_name} 为 {new_name}")
                    continue
                
                try:
                    shutil.move(str(temp_file), str(new_path))
                    backup_manager.record_operation("move", temp_file, new_path)
                    logger.info(f"重命名 {orig_name} 为 {new_name}")
                except Exception as e:
                    logger.error(f"重命名失败 {orig_name}: {e}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step8_compress(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤8：压缩叶目录（没有子目录且只包含JPG文件的目录）"""
    # 查找所有符合条件的叶目录
    leaf_dirs = []
    
    # 递归遍历所有目录
    for directory in root.rglob('*'):
        if not directory.is_dir() or directory.name in config["skip_dirs"]:
            continue
        
        # 检查是否包含子目录
        has_subdirs = any(
            item.is_dir() and item.name not in config["skip_dirs"]
            for item in directory.iterdir()
        )
        
        if has_subdirs:
            continue  # 有子目录的不是叶目录
        
        # 检查是否只包含JPG文件
        jpg_files = []
        valid_dir = True
        
        for item in directory.iterdir():
            if item.name in config["skip_dirs"]:
                continue
            
            if item.is_file():
                if item.suffix.lower() in ['.jpg', '.jpeg']:
                    jpg_files.append(item)
                else:
                    # 遇到非JPG文件，标记为无效
                    valid_dir = False
                    logger.debug(f"跳过目录 {directory}，包含非JPG文件: {item.name}")
                    break
            else:  # 遇到子目录（虽然前面检查过，但再次确认）
                valid_dir = False
                break
        
        if valid_dir and jpg_files:
            leaf_dirs.append(directory)
    
    # 按路径深度排序，确保先处理深层目录
    leaf_dirs.sort(key=lambda x: len(x.parts), reverse=True)
    
    total = len(leaf_dirs)
    logger.info(f"步骤8：找到 {total} 个叶目录需要压缩")
    
    if total == 0:
        logger.warning("步骤8：未找到需要压缩的叶目录")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将压缩 {total} 个叶目录为ZIP文件。确认继续?",
        config
    ):
        logger.info("步骤8：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, directory in enumerate(leaf_dirs):
        zip_file = directory.with_suffix('.zip')
        jpg_files = sorted([f for f in directory.glob('*.jpg')], key=natural_sort_key)
        
        if not config["dry_run"]:
            try:
                # 使用临时文件创建压缩包
                unique_id = uuid.uuid4().hex[:8]
                temp_zip = directory.with_suffix(f'.tmp_{unique_id}.zip')
                
                with zipfile.ZipFile(temp_zip, 'w', config["compress_level"]) as zf:
                    # 按自然顺序添加JPG文件
                    for file in jpg_files:
                        zf.write(file, arcname=file.name)
                        logger.debug(f"添加到ZIP: {file.name}")
                
                # 验证压缩包
                valid = False
                try:
                    with zipfile.ZipFile(temp_zip, 'r') as zf:
                        zip_contents = zf.namelist()
                        valid = len(zip_contents) == len(jpg_files)
                except Exception as e:
                    logger.error(f"验证ZIP文件失败 {temp_zip}: {e}")
                
                if not valid:
                    raise Exception(f"ZIP文件验证失败: {temp_zip}")
                
                # 重命名临时文件
                if temp_zip.exists():
                    if zip_file.exists():
                        zip_file.unlink()
                    temp_zip.rename(zip_file)
                    
                    # 记录操作
                    backup_manager.record_operation("create", zip_file)
                    
                    # 删除原始目录
                    shutil.rmtree(directory)
                    backup_manager.record_operation("delete", directory)
                    
                    logger.info(f"压缩 {directory} 为 {zip_file}")
            except Exception as e:
                logger.error(f"压缩失败 {directory}: {e}")
                
                # 清理临时文件
                if 'temp_zip' in locals() and Path(temp_zip).exists():
                    try:
                        Path(temp_zip).unlink()
                        logger.info(f"已清理无效的临时ZIP文件: {temp_zip}")
                    except Exception as cleanup_e:
                        logger.error(f"清理临时ZIP文件失败 {temp_zip}: {cleanup_e}")
                
                # 继续处理下一个目录
                continue
        else:
            logger.info(f"[DRY RUN] 将压缩 {directory} 为 {zip_file}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

def step9_rename_cbz(root: Path, progress: ProgressManager, config: ConfigManager, backup_manager: BackupManager):
    """步骤9：重命名ZIP为CBZ"""
    zip_files = [
        f for f in root.glob('*.zip')
        if f.is_file()
    ]
    
    total = len(zip_files)
    logger.info(f"步骤9：重命名 {total} 个ZIP文件为CBZ")
    
    if total == 0:
        logger.warning("步骤9：未找到ZIP文件")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    if not confirm_operation(
        f"即将重命名 {total} 个ZIP文件为CBZ格式。确认继续?",
        config
    ):
        logger.info("步骤9：用户取消了操作")
        progress.update_task(1.0)  # 确保任务进度100%
        return
    
    for idx, zip_file in enumerate(zip_files):
        cbz_file = zip_file.with_suffix('.cbz')
        
        if not config["dry_run"]:
            try:
                zip_file.rename(cbz_file)
                backup_manager.record_operation("rename", zip_file, cbz_file)
                logger.info(f"重命名 {zip_file} 为 {cbz_file}")
            except Exception as e:
                logger.error(f"重命名失败 {zip_file}: {e}")
        else:
            logger.info(f"[DRY RUN] 将重命名 {zip_file} 为 {cbz_file}")
        
        if total > 0:
            progress.update_task((idx+1)/total)
    
    progress.complete_step()  # 确保步骤完成时进度为100%

# ====================== 主程序 ======================
def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description='漫画处理工具')
    parser.add_argument('--batch', action='store_true', help='批处理模式（无交互）')
    parser.add_argument('--dry-run', action='store_true', help='模拟运行（不修改任何文件）')
    parser.add_argument('--no-backup', action='store_true', help='禁用备份')
    parser.add_argument('--start-num', type=int, help='起始编号（默认: 0）')
    parser.add_argument('--compress-level', type=str, help='压缩级别 (stored, deflated, bzip2, lzma)')
    parser.add_argument('--config', type=str, help='配置文件路径')
    parser.add_argument('--max-files', type=int, help='每个目录最大文件数')
    return parser.parse_args()

def main():
    global logger
    
    # 配置参数解析 - 由于在GUI中使用，我们不需要命令行参数
    # 但需要模拟参数解析的结果
    class Args:
        batch = False
        dry_run = False
        no_backup = False
        start_num = None
        compress_level = None
        config = None
        max_files = None
    
    args = Args()
    
    # 获取根目录
    root_dir = get_root()
    print(f"根目录: {root_dir.resolve()}")
    
    # 设置日志
    logger = setup_logging(root_dir)
    
    # Windows控制台支持
    if sys.platform == "win32":
        try:
            from ctypes import windll
            windll.kernel32.SetConsoleMode(windll.kernel32.GetStdHandle(-11), 7)
        except Exception as e:
            logger.warning(f"设置Windows控制台模式失败: {e}")
    
    # 初始化配置
    config_file = Path(args.config) if args.config else None
    config = ConfigManager(config_file)
    
    # 应用命令行参数覆盖配置
    if args.batch:
        config["interactive_mode"] = False
        config["skip_step_confirmations"] = True
    
    if args.dry_run:
        config["dry_run"] = True
    
    if args.no_backup:
        config["backup_enabled"] = False
    
    if args.start_num:
        config["start_num"] = args.start_num
    
    # 处理压缩级别参数
    if args.compress_level:
        level_map = {
            'stored': zipfile.ZIP_STORED,
            'deflated': zipfile.ZIP_DEFLATED,
            'bzip2': zipfile.ZIP_BZIP2,
            'lzma': zipfile.ZIP_LZMA
        }
        if args.compress_level.lower() in level_map:
            config["compress_level"] = level_map[args.compress_level.lower()]
        else:
            print(f"警告: 无效的压缩级别 '{args.compress_level}'，使用默认级别")
    
    if args.max_files:
        config["max_files_per_dir"] = args.max_files
    
    # 验证目录结构
    validator = DirectoryValidator(root_dir, config)
    is_valid, issues = validator.validate_structure()
    
    if not is_valid:
        print("\n目录结构验证失败，发现以下问题:")
        for issue in issues:
            print(f"- {issue}")
        
        if config["interactive_mode"]:
            confirm = input("\n仍然继续? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("操作已取消")
                return
        else:
            print("错误: 目录结构验证失败，退出处理")
            sys.exit(1)
    
    # 检查磁盘空间
    if not validator.validate_disk_space():
        if config["interactive_mode"]:
            confirm = input("\n磁盘空间警告，是否继续? [y/N]: ").strip().lower()
            if confirm != 'y':
                print("操作已取消")
                return
    
    # 创建备份
    backup_manager = BackupManager(root_dir, config)
    if config["backup_enabled"] and not config["dry_run"]:
        backup_path = backup_manager.create_backup()
        if not backup_path:
            print("警告: 备份创建失败，继续操作可能有风险")
            if config["interactive_mode"]:
                confirm = input("是否继续? [y/N]: ").strip().lower()
                if confirm != 'y':
                    print("操作已取消")
                    return
    
    # 显示配置摘要
    print_config_summary(config)
    
    # 用户确认
    if config["interactive_mode"] and not config["dry_run"]:
        while True:
            confirm = input("确认使用以上配置处理目录? [Y/n/e]: ").strip().lower()
            if confirm in ['', 'y']:
                # 保存确认的配置
                config.save_config()
                break
            elif confirm == 'e':
                # 进入配置编辑
                config.edit_interactively()
                # 重新显示配置摘要
                print_config_summary(config)
            else:
                print("操作已取消")
                return
    
    # 创建进度管理器
    progress = ProgressManager(total_steps=9, config=config)
    
    try:
        # 执行处理步骤
        step_functions = [
            step1_convert,
            step2_rename,
            step3_rename_subdirs,
            step4_add_prefix,
            step5_move_files,
            step6_clean_dirs,
            step7_final_rename,
            step8_compress,
            step9_rename_cbz
        ]
        
        step_names = [
            "转换非JPG图像",
            "四位数字重命名",
            "重命名次级目录",
            "添加目录名前缀",
            "移动文件到父目录",
            "清理空目录",
            "最终文件重命名",
            "压缩子目录",
            "重命名ZIP为CBZ"
        ]
        
        for step_func, step_name in zip(step_functions, step_names):
            progress.step_start(step_name)
            step_func(root_dir, progress, config, backup_manager)
        
        # 确保最后显示100%完成
        progress.complete_step()
        
        print("\n" * 5)  # 清除进度条
        print("✓ 处理完成！")
        logger.info("所有步骤完成")
        
        # 最终确认
        if not config["dry_run"]:
            if config["interactive_mode"]:
                print("\n处理已完成。如果结果不正确，您可以:")
                print("1. 检查日志文件获取详细信息")
                print("2. 使用备份恢复原始文件")
                input("按回车键退出...")
    
    except KeyboardInterrupt:
        print("\n" * 5)  # 清除进度条
        print("\n⚠ 操作被用户中断!")
        logger.warning("操作被用户中断")
        
        if config["interactive_mode"]:
            confirm = input("是否回滚已执行的操作? [y/N]: ").strip().lower()
            if confirm == 'y':
                backup_manager.rollback()
    
    except Exception as e:
        print("\n" * 5)  # 清除进度条
        logger.critical(f"程序崩溃: {str(e)}", exc_info=True)
        print(f"\n❌ 致命错误: {str(e)}")
        
        if config["interactive_mode"]:
            confirm = input("是否尝试回滚已执行的操作? [y/N]: ").strip().lower()
            if confirm == 'y':
                backup_manager.rollback()
        
        sys.exit(1)