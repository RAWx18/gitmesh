/**
 * Conversion Notes Panel Component
 * 
 * Displays and manages conversion notes and documentation
 * for CLI-to-web conversion operations.
 */

import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '../ui/card';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Textarea } from '../ui/textarea';
import { Badge } from '../ui/badge';
import { ScrollArea } from '../ui/scroll-area';
import { Separator } from '../ui/separator';
import { 
  Plus, 
  FileText, 
  AlertTriangle, 
  CheckCircle, 
  Info, 
  Lightbulb,
  Book,
  X,
  Edit,
  Save,
  Tag
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface ConversionNote {
  id: string;
  operation_id: string;
  note_type: 'info' | 'warning' | 'error' | 'success' | 'tip' | 'documentation';
  title: string;
  content: string;
  author: string;
  created_at: string;
  tags: string[];
  is_public: boolean;
}

interface ConversionOperation {
  id: string;
  operation_type: string;
  original_command: string;
  converted_equivalent?: string;
  status: string;
  conversion_notes?: string;
}

interface ConversionNotesPanelProps {
  operations: ConversionOperation[];
  currentUser: string;
  onNoteCreated?: (note: ConversionNote) => void;
}

export const ConversionNotesPanel: React.FC<ConversionNotesPanelProps> = ({
  operations,
  currentUser,
  onNoteCreated
}) => {
  const [notes, setNotes] = useState<ConversionNote[]>([]);
  const [selectedOperation, setSelectedOperation] = useState<string>('');
  const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state for creating notes
  const [newNote, setNewNote] = useState({
    note_type: 'info' as const,
    title: '',
    content: '',
    tags: [] as string[],
    is_public: true
  });

  // Fetch notes for all operations
  const fetchNotes = async () => {
    if (operations.length === 0) return;

    setIsLoading(true);
    try {
      const allNotes: ConversionNote[] = [];
      
      for (const operation of operations) {
        const response = await fetch(`/api/v1/conversion/operations/${operation.id}/notes`);
        if (response.ok) {
          const operationNotes = await response.json();
          allNotes.push(...operationNotes);
        }
      }
      
      setNotes(allNotes.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch notes');
    } finally {
      setIsLoading(false);
    }
  };

  // Create a new note
  const createNote = async () => {
    if (!selectedOperation || !newNote.title.trim() || !newNote.content.trim()) {
      return;
    }

    try {
      const response = await fetch(`/api/v1/conversion/operations/${selectedOperation}/notes`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          note_type: newNote.note_type,
          title: newNote.title,
          content: newNote.content,
          author: currentUser,
          tags: newNote.tags,
          is_public: newNote.is_public
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to create note');
      }

      const result = await response.json();
      
      // Reset form
      setNewNote({
        note_type: 'info',
        title: '',
        content: '',
        tags: [],
        is_public: true
      });
      setSelectedOperation('');
      setIsCreateDialogOpen(false);

      // Refresh notes
      await fetchNotes();

      // Notify parent
      if (onNoteCreated) {
        // We'd need to fetch the created note to get full details
        // For now, just refresh the list
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create note');
    }
  };

  // Get note type icon
  const getNoteTypeIcon = (type: string) => {
    switch (type) {
      case 'info':
        return <Info className="w-4 h-4 text-blue-600" />;
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-yellow-600" />;
      case 'error':
        return <X className="w-4 h-4 text-red-600" />;
      case 'success':
        return <CheckCircle className="w-4 h-4 text-green-600" />;
      case 'tip':
        return <Lightbulb className="w-4 h-4 text-purple-600" />;
      case 'documentation':
        return <Book className="w-4 h-4 text-indigo-600" />;
      default:
        return <FileText className="w-4 h-4 text-gray-600" />;
    }
  };

  // Get note type color
  const getNoteTypeColor = (type: string) => {
    switch (type) {
      case 'info':
        return 'bg-blue-50 border-blue-200';
      case 'warning':
        return 'bg-yellow-50 border-yellow-200';
      case 'error':
        return 'bg-red-50 border-red-200';
      case 'success':
        return 'bg-green-50 border-green-200';
      case 'tip':
        return 'bg-purple-50 border-purple-200';
      case 'documentation':
        return 'bg-indigo-50 border-indigo-200';
      default:
        return 'bg-gray-50 border-gray-200';
    }
  };

  // Add tag to new note
  const addTag = (tag: string) => {
    if (tag.trim() && !newNote.tags.includes(tag.trim())) {
      setNewNote(prev => ({
        ...prev,
        tags: [...prev.tags, tag.trim()]
      }));
    }
  };

  // Remove tag from new note
  const removeTag = (tagToRemove: string) => {
    setNewNote(prev => ({
      ...prev,
      tags: prev.tags.filter(tag => tag !== tagToRemove)
    }));
  };

  useEffect(() => {
    fetchNotes();
  }, [operations]);

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center space-x-2">
            <FileText className="w-5 h-5" />
            <span>Conversion Notes</span>
          </CardTitle>
          <Dialog open={isCreateDialogOpen} onOpenChange={setIsCreateDialogOpen}>
            <DialogTrigger asChild>
              <Button size="sm" disabled={operations.length === 0}>
                <Plus className="w-4 h-4 mr-2" />
                Add Note
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Create Conversion Note</DialogTitle>
                <DialogDescription>
                  Document insights, issues, or tips about CLI-to-web conversions.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4">
                {/* Operation Selection */}
                <div>
                  <label className="text-sm font-medium">Operation</label>
                  <Select value={selectedOperation} onValueChange={setSelectedOperation}>
                    <SelectTrigger>
                      <SelectValue placeholder="Select an operation" />
                    </SelectTrigger>
                    <SelectContent>
                      {operations.map((op) => (
                        <SelectItem key={op.id} value={op.id}>
                          <div className="flex items-center space-x-2">
                            <code className="text-xs bg-muted px-1 rounded">
                              {op.original_command}
                            </code>
                            <Badge variant="outline" className="text-xs">
                              {op.status}
                            </Badge>
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                {/* Note Type */}
                <div>
                  <label className="text-sm font-medium">Type</label>
                  <Select 
                    value={newNote.note_type} 
                    onValueChange={(value: any) => setNewNote(prev => ({ ...prev, note_type: value }))}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="info">
                        <div className="flex items-center space-x-2">
                          <Info className="w-4 h-4 text-blue-600" />
                          <span>Information</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="tip">
                        <div className="flex items-center space-x-2">
                          <Lightbulb className="w-4 h-4 text-purple-600" />
                          <span>Tip</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="warning">
                        <div className="flex items-center space-x-2">
                          <AlertTriangle className="w-4 h-4 text-yellow-600" />
                          <span>Warning</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="error">
                        <div className="flex items-center space-x-2">
                          <X className="w-4 h-4 text-red-600" />
                          <span>Error</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="success">
                        <div className="flex items-center space-x-2">
                          <CheckCircle className="w-4 h-4 text-green-600" />
                          <span>Success</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="documentation">
                        <div className="flex items-center space-x-2">
                          <Book className="w-4 h-4 text-indigo-600" />
                          <span>Documentation</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>

                {/* Title */}
                <div>
                  <label className="text-sm font-medium">Title</label>
                  <Input
                    value={newNote.title}
                    onChange={(e) => setNewNote(prev => ({ ...prev, title: e.target.value }))}
                    placeholder="Brief description of the note"
                  />
                </div>

                {/* Content */}
                <div>
                  <label className="text-sm font-medium">Content</label>
                  <Textarea
                    value={newNote.content}
                    onChange={(e) => setNewNote(prev => ({ ...prev, content: e.target.value }))}
                    placeholder="Detailed note content..."
                    rows={4}
                  />
                </div>

                {/* Tags */}
                <div>
                  <label className="text-sm font-medium">Tags</label>
                  <div className="flex flex-wrap gap-2 mb-2">
                    {newNote.tags.map((tag) => (
                      <Badge key={tag} variant="secondary" className="text-xs">
                        {tag}
                        <button
                          onClick={() => removeTag(tag)}
                          className="ml-1 hover:text-red-600"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </Badge>
                    ))}
                  </div>
                  <Input
                    placeholder="Add tags (press Enter)"
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        addTag(e.currentTarget.value);
                        e.currentTarget.value = '';
                      }
                    }}
                  />
                </div>
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={() => setIsCreateDialogOpen(false)}>
                  Cancel
                </Button>
                <Button 
                  onClick={createNote}
                  disabled={!selectedOperation || !newNote.title.trim() || !newNote.content.trim()}
                >
                  <Save className="w-4 h-4 mr-2" />
                  Create Note
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </CardHeader>

      <CardContent>
        {isLoading ? (
          <div className="text-center py-8 text-muted-foreground">
            Loading notes...
          </div>
        ) : error ? (
          <div className="text-center py-8 text-red-600">
            Error: {error}
          </div>
        ) : notes.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            No conversion notes yet. Create your first note to document insights and tips.
          </div>
        ) : (
          <ScrollArea className="h-96">
            <div className="space-y-4">
              {notes.map((note) => {
                const operation = operations.find(op => op.id === note.operation_id);
                
                return (
                  <div
                    key={note.id}
                    className={`p-4 rounded-lg border ${getNoteTypeColor(note.note_type)}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center space-x-2">
                        {getNoteTypeIcon(note.note_type)}
                        <h4 className="font-medium">{note.title}</h4>
                      </div>
                      <div className="text-xs text-muted-foreground">
                        {new Date(note.created_at).toLocaleDateString()}
                      </div>
                    </div>

                    {operation && (
                      <div className="mb-2">
                        <code className="text-xs bg-background/50 px-2 py-1 rounded">
                          {operation.original_command}
                        </code>
                      </div>
                    )}

                    <p className="text-sm mb-3 whitespace-pre-wrap">{note.content}</p>

                    <div className="flex items-center justify-between">
                      <div className="flex flex-wrap gap-1">
                        {note.tags.map((tag) => (
                          <Badge key={tag} variant="outline" className="text-xs">
                            <Tag className="w-3 h-3 mr-1" />
                            {tag}
                          </Badge>
                        ))}
                      </div>
                      <div className="text-xs text-muted-foreground">
                        by {note.author}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </CardContent>
    </Card>
  );
};

export default ConversionNotesPanel;