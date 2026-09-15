//go:build unix

package session

import (
	"os/exec"
	"syscall"
)

// setProcessGroup puts the child in its own process group so a stop can take
// down whatever it spawned.
//
// The service is started through a wrapper (`uv run uvicorn ...`, or a checkout's
// .venv/bin/python -m uvicorn), and uvicorn spawns reloader workers of its own.
// Killing only the direct child leaves those grandchildren holding the inherited
// stdout pipe open, so a reader goroutine never sees EOF and the caller blocks
// until they exit on their own -- the timeout is silently skipped and the UI
// looks frozen after the user asked it to stop.
func setProcessGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

// killProcessGroup signals the whole group, which closes inherited pipes
// immediately instead of waiting for grandchildren to exit.
func killProcessGroup(cmd *exec.Cmd) error {
	if cmd.Process == nil {
		return nil
	}
	if err := syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL); err != nil {
		return cmd.Process.Kill()
	}
	return nil
}
