export type RecordRow = Record<string, unknown>;

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  tables?: Array<{ title: string; data: RecordRow[] }>;
  charts?: Array<Record<string, unknown>>;
  warnings?: string[];
  error?: boolean;
  createdAt: string;
};

export type Workspace = {
  filename: string;
  records: RecordRow[];
  messages: ChatMessage[];
};

const DATABASE_NAME = "ai-data-analyst-workspace";
const STORE_NAME = "workspace";
const WORKSPACE_KEY = "current";

function openWorkspaceDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => {
      request.result.createObjectStore(STORE_NAME);
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open local workspace storage."));
    request.onblocked = () => reject(new Error("Workspace storage is blocked by another browser tab."));
  });
}

export async function readWorkspace(): Promise<Workspace | null> {
  const database = await openWorkspaceDatabase();
  try {
    return await new Promise((resolve, reject) => {
      const request = database
        .transaction(STORE_NAME, "readonly")
        .objectStore(STORE_NAME)
        .get(WORKSPACE_KEY);
      request.onsuccess = () => resolve((request.result as Workspace | undefined) ?? null);
      request.onerror = () => reject(request.error ?? new Error("Could not load the local workspace."));
    });
  } finally {
    database.close();
  }
}

export async function writeWorkspace(workspace: Workspace): Promise<void> {
  const database = await openWorkspaceDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).put(workspace, WORKSPACE_KEY);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Could not save the local workspace."));
      transaction.onabort = () => reject(transaction.error ?? new Error("Saving the local workspace was cancelled."));
    });
  } finally {
    database.close();
  }
}

export async function clearWorkspace(): Promise<void> {
  const database = await openWorkspaceDatabase();
  try {
    await new Promise<void>((resolve, reject) => {
      const transaction = database.transaction(STORE_NAME, "readwrite");
      transaction.objectStore(STORE_NAME).delete(WORKSPACE_KEY);
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error ?? new Error("Could not clear the local workspace."));
      transaction.onabort = () => reject(transaction.error ?? new Error("Clearing the local workspace was cancelled."));
    });
  } finally {
    database.close();
  }
}
