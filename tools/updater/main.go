//go:build windows

// MikanCL 更新器（mcu.exe）。
//
// 启动器把新版本下载到临时目录后，把这个小工具解压出来并带上参数运行；
// 由它等待启动器退出、备份旧 exe、把新 exe 换上去、可选重启，最后清理
// 临时文件并自毁。用纯标准库实现，不依赖任何第三方 Go 模块。
//
// 用法：
//
//	mcu.exe -target C:\path\MikanCL.exe -source %TEMP%\mikancl-update-xxx\MikanCL.exe \
//	        -pid 1234 -restart -cleanup %TEMP%\mikancl-update-xxx -log %TEMP%\mcu.log
package main

import (
	"flag"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"syscall"
	"time"
	"unsafe"
)

const (
	moveFileReplaceExisting   = 0x1
	moveFileDelayUntilReboot  = 0x4
	createNoWindow            = 0x08000000
	detachedProcess           = 0x00000008
	createNewProcessGroup     = 0x00000200
	synchronizeAccess         = 0x00100000
	waitObject0               = 0x00000000
	waitTimeoutCode           = 0x00000102
	defaultWaitSeconds        = 240
	replaceRetrySeconds       = 60
	updaterVersion            = "1.0.0"
)

var (
	kernel32        = syscall.NewLazyDLL("kernel32.dll")
	procMoveFileExW = kernel32.NewProc("MoveFileExW")
)

type logger struct {
	file *os.File
	path string
}

func newLogger(path string) *logger {
	log := &logger{path: path}
	if path == "" {
		return log
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return log
	}
	file, err := os.OpenFile(path, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return log
	}
	log.file = file
	return log
}

func (l *logger) printf(format string, args ...any) {
	line := fmt.Sprintf("%s %s\r\n", time.Now().Format("2006-01-02 15:04:05"), fmt.Sprintf(format, args...))
	if l.file != nil {
		_, _ = l.file.WriteString(line)
		_ = l.file.Sync()
	}
}

func (l *logger) close() {
	if l.file != nil {
		_ = l.file.Close()
		l.file = nil
	}
}

func moveFileEx(from, to string, flags uint32) error {
	src, err := syscall.UTF16PtrFromString(from)
	if err != nil {
		return err
	}
	var dst *uint16
	if to != "" {
		dst, err = syscall.UTF16PtrFromString(to)
		if err != nil {
			return err
		}
	}
	r, _, callErr := procMoveFileExW.Call(
		uintptr(unsafe.Pointer(src)),
		uintptr(unsafe.Pointer(dst)),
		uintptr(flags),
	)
	if r == 0 {
		if callErr != nil && callErr != syscall.Errno(0) {
			return callErr
		}
		return syscall.EINVAL
	}
	return nil
}

// waitProcess 等目标进程退出；进程不存在也视为已退出。
func waitProcess(pid int, timeout time.Duration, log *logger) bool {
	if pid <= 0 {
		return true
	}
	handle, err := syscall.OpenProcess(synchronizeAccess, false, uint32(pid))
	if err != nil {
		log.printf("进程 %d 已不可打开（可能已退出）：%v", pid, err)
		return true
	}
	defer syscall.CloseHandle(handle)
	deadline := time.Now().Add(timeout)
	for {
		event, err := syscall.WaitForSingleObject(handle, 500)
		if err == nil && event == waitObject0 {
			log.printf("进程 %d 已退出", pid)
			return true
		}
		if time.Now().After(deadline) {
			log.printf("等待进程 %d 超时（%s），强行继续", pid, timeout)
			return false
		}
	}
}

func looksLikeExe(path string) bool {
	file, err := os.Open(path)
	if err != nil {
		return false
	}
	defer file.Close()
	head := make([]byte, 2)
	if _, err := io.ReadFull(file, head); err != nil {
		return false
	}
	return head[0] == 'M' && head[1] == 'Z'
}

// copyFile 复制并 fsync，避免关机/崩溃时留下半截 exe。
func copyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := os.MkdirAll(filepath.Dir(dst), 0o755); err != nil {
		return err
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o755)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		_ = out.Close()
		return err
	}
	if err := out.Sync(); err != nil {
		_ = out.Close()
		return err
	}
	return out.Close()
}

// replaceWithRetry 反复尝试把 staged 换到 target 上，直到成功或超时。
func replaceWithRetry(staged, target string, timeout time.Duration, log *logger) error {
	deadline := time.Now().Add(timeout)
	var last error
	for {
		// 优先原子替换；失败再走"改名字腾位子"的老办法。
		if err := moveFileEx(staged, target, moveFileReplaceExisting); err == nil {
			return nil
		} else {
			last = err
		}
		if err := os.Rename(staged, target); err == nil {
			return nil
		} else {
			last = err
		}
		if time.Now().After(deadline) {
			return last
		}
		time.Sleep(300 * time.Millisecond)
	}
}

func startDetached(path, workDir string) error {
	cmd := exec.Command(path)
	cmd.Dir = workDir
	cmd.SysProcAttr = &syscall.SysProcAttr{
		CreationFlags: detachedProcess | createNewProcessGroup,
	}
	cmd.Stdin = nil
	cmd.Stdout = nil
	cmd.Stderr = nil
	return cmd.Start()
}

func deleteWithRetry(path string, timeout time.Duration) bool {
	deadline := time.Now().Add(timeout)
	for {
		if err := os.Remove(path); err == nil || os.IsNotExist(err) {
			return true
		}
		if time.Now().After(deadline) {
			return false
		}
		time.Sleep(250 * time.Millisecond)
	}
}

// spawnDetached 直接用 CreateProcess 起一个没有窗口的 cmd，绕开
// exec.Command 对参数里引号的转义（那会把 del 的路径搞坏）。
func spawnDetached(cmdLine string) (int, error) {
	line, err := syscall.UTF16PtrFromString(cmdLine)
	if err != nil {
		return 0, err
	}
	var startup syscall.StartupInfo
	startup.Cb = uint32(unsafe.Sizeof(startup))
	var info syscall.ProcessInformation
	flags := uint32(createNoWindow | createNewProcessGroup)
	if err := syscall.CreateProcess(nil, line, nil, nil, false, flags, nil, nil, &startup, &info); err != nil {
		return 0, err
	}
	defer syscall.CloseHandle(info.Process)
	defer syscall.CloseHandle(info.Thread)
	return int(info.ProcessId), nil
}

// selfDestruct 删掉自己。运行中的 exe 不能被删除，但允许改名，所以顺序是：
//  1. 直接删（非运行态 / 被外部调用时能成功）
//  2. 改名让位（挪进临时目录的 .tmp 或原地加后缀），后续就能被删掉
//  3. 登记重启后删除兜底
//  4. 挂一个极短的 cmd 尾巴，在进程退出后删文件 + 删目录
//
// 万一 cmd 被安全软件拦下，启动器下次启动也会清理这些残留（见 update.cleanup_old_files）。
func selfDestruct(log *logger, cleanupDir string, enabled bool) {
	if !enabled {
		log.printf("按参数保留更新器自身，跳过自毁")
		log.close()
		return
	}
	self, err := os.Executable()
	if err != nil {
		log.close()
		return
	}
	if abs, absErr := filepath.Abs(self); absErr == nil {
		self = abs
	}
	if err := os.Remove(self); err == nil {
		log.printf("更新器已直接删除自身")
		log.close()
		if cleanupDir != "" {
			_ = os.RemoveAll(cleanupDir)
		}
		return
	} else {
		log.printf("直接删除自身失败（%v），改用改名 + 延迟删除", err)
	}

	renamed := self
	stamp := time.Now().UnixNano()
	candidates := []string{fmt.Sprintf("%s.mcu-%d.tmp", self, stamp)}
	if cleanupDir != "" {
		candidates = append(candidates, filepath.Join(cleanupDir, fmt.Sprintf("mcu-%d.tmp", stamp)))
	}
	for _, candidate := range candidates {
		if renameErr := os.Rename(self, candidate); renameErr == nil {
			renamed = candidate
			log.printf("更新器已改名待删：%s", candidate)
			break
		}
	}
	if err := moveFileEx(renamed, "", moveFileDelayUntilReboot); err != nil {
		log.printf("登记重启后删除失败：%v", err)
	} else {
		log.printf("已登记重启后删除：%s", renamed)
	}

	ping := filepath.Join(os.Getenv("SystemRoot"), "System32", "ping.exe")
	if _, statErr := os.Stat(ping); statErr != nil {
		ping = "ping"
	}
	command := fmt.Sprintf("\"%s\" -n 2 127.0.0.1 >nul & del /f /q \"%s\"", ping, renamed)
	if cleanupDir != "" {
		command += fmt.Sprintf(" & rmdir /s /q \"%s\"", cleanupDir)
	}
	if pid, err := spawnDetached("cmd.exe /c " + command); err != nil {
		log.printf("自毁命令启动失败：%v", err)
	} else {
		log.printf("已启动自毁命令（pid %d）", pid)
	}
	log.close()
}

func main() {
	var (
		target   = flag.String("target", "", "要替换的启动器 exe 路径")
		source   = flag.String("source", "", "下载好的新 exe 路径")
		pid      = flag.Int("pid", 0, "正在运行的启动器进程号，0 表示不等待")
		restart  = flag.Bool("restart", true, "替换完成后重新打开启动器")
		cleanup  = flag.String("cleanup", "", "完成后要删掉的临时目录")
		logPath  = flag.String("log", "", "日志文件路径")
		waitSecs = flag.Int("wait", defaultWaitSeconds, "等待启动器退出的秒数")
		version  = flag.Bool("version", false, "打印版本")
		keepSelf = flag.Bool("keepself", false, "保留更新器自身（调试用，不自毁）")
	)
	flag.Parse()

	if *version {
		fmt.Printf("mcu %s\n", updaterVersion)
		return
	}
	log := newLogger(*logPath)
	log.printf("更新器 %s 启动：target=%q source=%q pid=%d restart=%v", updaterVersion, *target, *source, *pid, *restart)

	if *target == "" || *source == "" {
		log.printf("参数不完整，放弃")
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	targetPath, err := filepath.Abs(*target)
	if err != nil {
		log.printf("target 路径非法：%v", err)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	sourcePath, err := filepath.Abs(*source)
	if err != nil {
		log.printf("source 路径非法：%v", err)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	if !looksLikeExe(sourcePath) {
		log.printf("新文件不是有效的 exe：%s", sourcePath)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	if info, statErr := os.Stat(sourcePath); statErr != nil || info.Size() < 128*1024 {
		log.printf("新文件过小或不完整：%v", statErr)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}

	waitProcess(*pid, time.Duration(*waitSecs)*time.Second, log)

	targetDir := filepath.Dir(targetPath)
	staged := filepath.Join(targetDir, fmt.Sprintf(".mikan-update-%d.exe", time.Now().UnixNano()))
	if err := copyFile(sourcePath, staged); err != nil {
		log.printf("暂存新版本失败（%s）：%v", staged, err)
		_ = os.Remove(staged)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	log.printf("新版本已暂存：%s", staged)

	backup := ""
	if _, statErr := os.Stat(targetPath); statErr == nil {
		backup = fmt.Sprintf("%s.old-%s", targetPath, time.Now().Format("20060102-150405"))
		if err := moveFileEx(targetPath, backup, moveFileReplaceExisting); err != nil {
			if renameErr := os.Rename(targetPath, backup); renameErr != nil {
				log.printf("备份旧版本失败：%v / %v", err, renameErr)
				backup = ""
			}
		}
		if backup != "" {
			log.printf("旧版本已备份：%s", backup)
		}
	}

	if err := replaceWithRetry(staged, targetPath, replaceRetrySeconds*time.Second, log); err != nil {
		log.printf("替换失败：%v", err)
		// 尽力还原旧版本，避免把用户的启动器弄丢
		if backup != "" {
			if rbErr := moveFileEx(backup, targetPath, moveFileReplaceExisting); rbErr == nil {
				log.printf("已回滚到旧版本")
			}
		}
		_ = os.Remove(staged)
		selfDestruct(log, *cleanup, !*keepSelf)
		return
	}
	log.printf("替换完成：%s", targetPath)

	if *restart {
		if err := startDetached(targetPath, targetDir); err != nil {
			log.printf("重启启动器失败：%v", err)
		} else {
			log.printf("已重新打开启动器")
		}
	}

	if backup != "" && !deleteWithRetry(backup, 15*time.Second) {
		log.printf("旧版本暂时删不掉，已登记重启后删除")
		_ = moveFileEx(backup, "", moveFileDelayUntilReboot)
	}
	// 顺便擦掉上次残留的旧版本
	if leftovers, globErr := filepath.Glob(targetPath + ".old-*"); globErr == nil {
		for _, item := range leftovers {
			deleteWithRetry(item, 2*time.Second)
		}
	}
	log.printf("全部完成，准备自毁")
	selfDestruct(log, *cleanup, !*keepSelf)
}
