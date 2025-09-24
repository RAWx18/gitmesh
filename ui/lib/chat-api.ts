const API_BASE_URL = 'http://localhost:8000/api/v1';

export interface ChatMessage {
  id: string;
  type: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  files?: string[];
  model?: string;
  metadata?: {
    confidence?: number;
    knowledge_used?: number;
    sources_count?: number;
    cosmos_available?: boolean;
  };
  codeSnippets?: Array<{
    language: string;
    code: string;
    filePath?: string;
  }>;
}

export interface ChatSession {
  id: string;
  title: string;
  repositoryId?: string;
  branch?: string;
  messages: ChatMessage[];
  selectedFiles: Array<{branch: string, path: string, content: string}>;
  createdAt: Date;
  updatedAt: Date;
}

export interface Context {
  id: string;
  files: Array<{
    path: string;
    content: string;
    branch: string;
    repository_id?: string;
    owner?: string;
    repo?: string;
    url?: string;
    raw_url?: string;
  }>;
  sources: string[];
  repositoryId?: string;
  branch?: string;
  totalTokens: number;
  createdAt: Date;
  updatedAt: Date;
}

export interface ContextStats {
  totalFiles: number;
  totalSources: number;
  totalTokens: number;
  averageTokensPerFile: number;
  createdAt: Date;
  updatedAt: Date;
}

class ChatAPI {
  private token: string;

  constructor(token: string) {
    this.token = token;
  }

  private async makeRequest(endpoint: string, options: RequestInit = {}) {
    const url = `${API_BASE_URL}${endpoint}`;
    
    console.log(`ChatAPI: Making request to ${url}`);
    console.log(`ChatAPI: Using token: ${this.token ? 'Token available' : 'No token'}`);
    
    const config: RequestInit = {
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.token}`,
        ...options.headers,
      },
      ...options,
    };

    try {
      const response = await fetch(url, config);
      
      console.log(`ChatAPI: Response status: ${response.status}`);
      
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error(`ChatAPI: Error response:`, errorData);
        
        // Handle different error response formats
        let errorMessage = `HTTP error! status: ${response.status}`;
        
        if (errorData) {
          if (typeof errorData === 'string') {
            errorMessage = errorData;
          } else if (errorData.error) {
            errorMessage = typeof errorData.error === 'string' ? errorData.error : JSON.stringify(errorData.error);
          } else if (errorData.detail) {
            errorMessage = typeof errorData.detail === 'string' ? errorData.detail : JSON.stringify(errorData.detail);
          } else if (errorData.message) {
            errorMessage = typeof errorData.message === 'string' ? errorData.message : JSON.stringify(errorData.message);
          }
        }
        
        throw new Error(errorMessage);
      }

      return await response.json();
    } catch (error) {
      console.error(`API request failed for ${endpoint}:`, error);
      
      // Ensure we always throw a proper Error with a string message
      if (error instanceof Error) {
        throw error;
      } else {
        throw new Error(`API request failed: ${String(error)}`);
      }
    }
  }

  // Chat Session Management
  async createSession(data: {
    title?: string;
    repositoryId?: string;
    branch?: string;
  }): Promise<{ success: boolean; session: ChatSession }> {
    return this.makeRequest('/chat/sessions', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getSession(sessionId: string): Promise<{ success: boolean; session: ChatSession }> {
    return this.makeRequest(`/chat/sessions/${sessionId}`);
  }

  async updateSession(sessionId: string, updates: Partial<ChatSession>): Promise<{ success: boolean; session: ChatSession }> {
    return this.makeRequest(`/chat/sessions/${sessionId}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
  }

  async deleteSession(sessionId: string): Promise<{ success: boolean; message: string }> {
    return this.makeRequest(`/chat/sessions/${sessionId}`, {
      method: 'DELETE',
    });
  }

  async getUserSessions(userId: string): Promise<{ success: boolean; sessions: ChatSession[] }> {
    return this.makeRequest(`/chat/users/${userId}/sessions`);
  }

  // Chat Messages
  async sendMessage(sessionId: string, data: {
    message: string;
    model?: string;
    context?: {
      files?: Array<{
        path: string;
        content: string;
        branch: string;
        repository_id?: string;
        owner?: string;
        repo?: string;
        url?: string;
        raw_url?: string;
      }>;
    };
    repository_id?: string;
  }): Promise<{
    success: boolean;
    userMessage: ChatMessage;
    assistantMessage: ChatMessage;
    session: ChatSession;
  }> {
    return this.makeRequest(`/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify(data),
    });
  }

  async getChatHistory(sessionId: string): Promise<{
    success: boolean;
    messages: ChatMessage[];
    session: ChatSession;
  }> {
    return this.makeRequest(`/chat/sessions/${sessionId}/messages`);
  }

  // Context Management (now part of chat sessions)
  async getSessionContextStats(sessionId: string): Promise<{ success: boolean; stats: ContextStats }> {
    return this.makeRequest(`/chat/sessions/${sessionId}/context/stats`);
  }

  async updateSessionContext(sessionId: string, data: {
    action: 'add_files' | 'remove_files' | 'clear_files';
    files?: Array<{path: string, content: string, branch: string}>;
  }): Promise<{ success: boolean; session: ChatSession }> {
    return this.makeRequest(`/chat/sessions/${sessionId}/context`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }
}

export default ChatAPI;