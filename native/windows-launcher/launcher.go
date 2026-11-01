// Smash AI Pro - native Windows launcher (v1.0.0)
// Opens the studio in its own app window via Edge/Chrome --app mode;
// falls back to the default browser. No console, branded icon embedded.
package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

const appURL = "https://my-ai-pro-rkxe.onrender.com"

func try(paths []string, args ...string) bool {
	for _, p := range paths {
		if p == "" {
			continue
		}
		if _, err := os.Stat(p); err == nil {
			cmd := exec.Command(p, args...)
			if err := cmd.Start(); err == nil {
				return true
			}
		}
	}
	return false
}

func main() {
	pf := os.Getenv("ProgramFiles")
	pf86 := os.Getenv("ProgramFiles(x86)")
	la := os.Getenv("LocalAppData")
	appArgs := []string{"--app=" + appURL, "--window-size=1360,900"}
	edge := []string{
		filepath.Join(pf, "Microsoft", "Edge", "Application", "msedge.exe"),
		filepath.Join(pf86, "Microsoft", "Edge", "Application", "msedge.exe"),
	}
	chrome := []string{
		filepath.Join(pf, "Google", "Chrome", "Application", "chrome.exe"),
		filepath.Join(pf86, "Google", "Chrome", "Application", "chrome.exe"),
		filepath.Join(la, "Google", "Chrome", "Application", "chrome.exe"),
	}
	if try(edge, appArgs...) || try(chrome, appArgs...) {
		return
	}
	sysroot := os.Getenv("SystemRoot")
	if try([]string{filepath.Join(sysroot, "System32", "rundll32.exe")}, "url.dll,FileProtocolHandler", appURL) {
		return
	}
	fmt.Println("Please open " + appURL + " in your browser.")
}
