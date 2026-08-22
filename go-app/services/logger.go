package services

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"runtime"
	"runtime/debug"
	"sync"
	"time"
)

// Logger is a global date-wise structured logging utility for Go microservices with traceback support.
type Logger struct {
	category    string
	subsystem   string
	mu          sync.Mutex
	currentDate string
	mainFile    *os.File
	errFile     *os.File
	stdLogger   *log.Logger
	errLogger   *log.Logger
}

var globalGoLogger *Logger
var onceGoLogger sync.Once

// GetLogger initializes or retrieves the global Go Logger instance.
func GetLogger() *Logger {
	onceGoLogger.Do(func() {
		globalGoLogger = NewLogger("GO_ENGINE", "CORE")
	})
	return globalGoLogger
}

// NewLogger creates a new Logger instance for a specific Go subsystem.
func NewLogger(category, subsystem string) *Logger {
	l := &Logger{
		category:  category,
		subsystem: subsystem,
	}
	l.initLogFiles()
	return l
}

func (l *Logger) initLogFiles() {
	l.mu.Lock()
	defer l.mu.Unlock()

	today := time.Now().Format("2006-01-02")
	if l.currentDate == today && l.mainFile != nil {
		return
	}

	if l.mainFile != nil {
		l.mainFile.Close()
	}
	if l.errFile != nil {
		l.errFile.Close()
	}

	baseDir := os.Getenv("LOG_DIR")
	if baseDir == "" {
		baseDir = "logs"
	}
	goLogDir := filepath.Join(baseDir, "go")
	os.MkdirAll(goLogDir, 0755)

	mainPath := filepath.Join(goLogDir, fmt.Sprintf("%s.log", today))
	errPath := filepath.Join(goLogDir, fmt.Sprintf("errors_%s.log", today))

	mainF, err := os.OpenFile(mainPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		mainF = nil
	}

	errF, err := os.OpenFile(errPath, os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0644)
	if err != nil {
		errF = nil
	}

	l.mainFile = mainF
	l.errFile = errF
	l.currentDate = today

	var mainW io.Writer = os.Stdout
	if mainF != nil {
		mainW = io.MultiWriter(os.Stdout, mainF)
	}

	var errW io.Writer = os.Stderr
	if errF != nil {
		errW = io.MultiWriter(os.Stderr, errF)
	}

	l.stdLogger = log.New(mainW, "", log.LstdFlags)
	l.errLogger = log.New(errW, "", log.LstdFlags)
}

func (l *Logger) checkRotation() {
	today := time.Now().Format("2006-01-02")
	if l.currentDate != today {
		l.initLogFiles()
	}
}

// Info logs an informational message.
func (l *Logger) Info(format string, v ...interface{}) {
	l.checkRotation()
	msg := fmt.Sprintf(format, v...)
	l.stdLogger.Printf("[INFO] [%s:%s] %s", l.category, l.subsystem, msg)
}

// Warning logs a warning message.
func (l *Logger) Warning(format string, v ...interface{}) {
	l.checkRotation()
	msg := fmt.Sprintf(format, v...)
	l.stdLogger.Printf("[WARN] [%s:%s] %s", l.category, l.subsystem, msg)
}

// Error logs an error message with file line reference to daily and error log files.
func (l *Logger) Error(err error, format string, v ...interface{}) {
	l.checkRotation()
	_, file, line, _ := runtime.Caller(1)
	msg := fmt.Sprintf(format, v...)
	fullMsg := fmt.Sprintf("[ERROR] [%s:%s] [%s:%d] %s | err: %v", l.category, l.subsystem, filepath.Base(file), line, msg, err)
	l.stdLogger.Println(fullMsg)
	l.errLogger.Println(fullMsg)
}

// Exception logs an error with full goroutine stack trace to daily and error log files.
func (l *Logger) Exception(err error, format string, v ...interface{}) {
	l.checkRotation()
	_, file, line, _ := runtime.Caller(1)
	msg := fmt.Sprintf(format, v...)
	stack := string(debug.Stack())
	fullMsg := fmt.Sprintf("[EXCEPTION] [%s:%s] [%s:%d] %s | err: %v\n--- Stack Trace ---\n%s\n-------------------", l.category, l.subsystem, filepath.Base(file), line, msg, err, stack)
	l.stdLogger.Println(fullMsg)
	l.errLogger.Println(fullMsg)
}
