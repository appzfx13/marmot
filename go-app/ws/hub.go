package ws

import "log"

// Hub maintains active clients and broadcasts messages.
type Hub struct {
	clients     map[*Client]bool
	taskSubs    map[string]map[*Client]bool
	Broadcast   chan []byte
	Register    chan *Client
	Unregister  chan *Client
	Subscribe   chan *TaskSubscription
	Unsubscribe chan *TaskSubscription
	TaskMessage chan *TaskMessage
}

// TaskSubscription represents a client subscribing to updates for a specific task.
type TaskSubscription struct {
	TaskID string
	Client *Client
}

// TaskMessage represents a message targeted to a specific task's subscribers.
type TaskMessage struct {
	TaskID string
	Data   []byte
}

// NewHub creates a new Hub instance.
func NewHub() *Hub {
	return &Hub{
		clients:     make(map[*Client]bool),
		taskSubs:    make(map[string]map[*Client]bool),
		Broadcast:   make(chan []byte),
		Register:    make(chan *Client),
		Unregister:  make(chan *Client),
		Subscribe:   make(chan *TaskSubscription),
		Unsubscribe: make(chan *TaskSubscription),
		TaskMessage: make(chan *TaskMessage),
	}
}

// Run starts the Hub loop to manage connections and subscriptions.
func (h *Hub) Run() {
	for {
		select {
		case client := <-h.Register:
			h.clients[client] = true
		case client := <-h.Unregister:
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				for taskID, subs := range h.taskSubs {
					delete(subs, client)
					if len(subs) == 0 {
						delete(h.taskSubs, taskID)
					}
				}
				close(client.send)
			}
		case sub := <-h.Subscribe:
			if h.taskSubs[sub.TaskID] == nil {
				h.taskSubs[sub.TaskID] = make(map[*Client]bool)
			}
			h.taskSubs[sub.TaskID][sub.Client] = true
		case unsub := <-h.Unsubscribe:
			if subs, ok := h.taskSubs[unsub.TaskID]; ok {
				delete(subs, unsub.Client)
				if len(subs) == 0 {
					delete(h.taskSubs, unsub.TaskID)
				}
			}
		case message := <-h.Broadcast:
			for client := range h.clients {
				select {
				case client.send <- message:
				default:
					close(client.send)
					delete(h.clients, client)
				}
			}
		case tm := <-h.TaskMessage:
			subs, ok := h.taskSubs[tm.TaskID]
			if !ok {
				log.Printf("🔕 [WS] No subscribers for task %s\n", tm.TaskID)
				continue
			}
			log.Printf("📤 [WS] Broadcasting to %d subscriber(s) for task %s\n", len(subs), tm.TaskID)
			for client := range subs {
				if _, stillConnected := h.clients[client]; stillConnected {
					select {
					case client.send <- tm.Data:
					default:
						close(client.send)
						delete(h.clients, client)
					}
				}
			}
		}
	}
}

// BroadcastToTask queues a message for clients subscribed to the given taskID.
func (h *Hub) BroadcastToTask(taskID string, message []byte) {
	h.TaskMessage <- &TaskMessage{TaskID: taskID, Data: message}
}
