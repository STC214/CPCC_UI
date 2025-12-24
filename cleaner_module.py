# 将原cleaner.py内容封装为模块
import os
import sys
import traceback

def main():
    """清理目录中的特定文件，如没有适配的文件则跳过清理步骤"""
    try:
        # 获取当前程序所在目录
        if getattr(sys, 'frozen', False):
            # 打包后的应用
            current_dir = os.path.dirname(sys.executable)
        else:
            # 开发环境
            current_dir = os.path.dirname(os.path.abspath(__file__))
        
        print(f"开始清理目录: {current_dir}")
        
        # 检查目录是否存在
        if not os.path.exists(current_dir):
            print(f"⚠️ 警告: 目录不存在 - {current_dir}")
            print("跳过清理步骤，继续后续处理...")
            return
        
        # 检查是否有需要清理的文件，避免不必要的遍历
        has_icon_files = False
        has_webp_files = False
        
        # 先简单检查是否有需要清理的文件类型
        for root, dirs, files in os.walk(current_dir):
            for file in files:
                if file == "icon.png":
                    has_icon_files = True
                elif file.lower().endswith('.webp') and ('(' in file or ')' in file):
                    has_webp_files = True
            # 如果两种类型的文件都找到了，可以提前结束检查
            if has_icon_files and has_webp_files:
                break
        
        # 如果没有任何需要清理的文件，直接跳过
        if not has_icon_files and not has_webp_files:
            print("ℹ️ 未找到需要清理的文件(icon.png或含括号的webp文件)")
            print("跳过清理步骤，继续后续处理...")
            return
        
        # 统计删除的文件数量
        icon_count = 0
        webp_count = 0
        
        # 遍历当前目录及其所有子目录
        for root, dirs, files in os.walk(current_dir):
            for file in files:
                file_path = os.path.join(root, file)
                
                # 检查是否为icon.png
                if file == "icon.png":
                    print(f"🗑️ 删除 icon.png 文件: {file_path}")
                    try:
                        os.remove(file_path)
                        icon_count += 1
                    except Exception as e:
                        print(f"❌ 删除文件时出错 {file_path}: {e}")
                
                # 检查是否为webp文件且文件名包含英文括号
                elif file.lower().endswith('.webp') and ('(' in file or ')' in file):
                    print(f"🗑️ 删除包含括号的webp文件: {file_path}")
                    try:
                        os.remove(file_path)
                        webp_count += 1
                    except Exception as e:
                        print(f"❌ 删除文件时出错 {file_path}: {e}")
        
        print(f"\n✅ 清理完成!")
        if icon_count > 0:
            print(f"共删除 {icon_count} 个 icon.png 文件")
        if webp_count > 0:
            print(f"共删除 {webp_count} 个含括号的webp文件")
        if icon_count == 0 and webp_count == 0:
            print("未删除任何文件")
    
    except Exception as e:
        print(f"❌ 清理过程中发生未预期错误:")
        print(f"{str(e)}")
        print(f"{traceback.format_exc()}")
        print("⚠️ 跳过清理步骤，继续后续处理...")