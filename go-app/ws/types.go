package ws

type SubscriptionMessage struct {
	Type     string `json:"type"`
	TaskID   string `json:"task_id"`
}

type ProgressMessage struct {
	Type     string  `json:"type"`
	TaskID   string  `json:"task_id"`
	Progress int     `json:"progress"`
	Status   string  `json:"status"`
	FileSize float64 `json:"file_size_mb,omitempty"`
	FilePath string  `json:"file_path,omitempty"`
	Error    string  `json:"error,omitempty"`
}
