"use client";

import { useState, useCallback, useEffect, createContext, useContext } from "react";

interface Toast {
  id: string;
  message: string;
}

interface ToastContextType {
  addToast: (message: string) => void;
}

export const ToastContext = createContext<ToastContextType>({
  addToast: () => {},
});

export function useToast() {
  return useContext(ToastContext);
}

export default function ErrorToastRegion() {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const addToast = useCallback((message: string) => {
    const id = Math.random().toString(36).slice(2);
    setToasts((prev) => {
      const next = [...prev, { id, message }];
      // Max 3 stacked; evict oldest
      return next.length > 3 ? next.slice(next.length - 3) : next;
    });
    // Auto-dismiss after 6 s
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 6000);
  }, []);

  const dismiss = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  return (
    <ToastContext.Provider value={{ addToast }}>
      <div className="fixed top-4 right-4 z-50 flex flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="bg-red-600 text-white px-4 py-3 rounded shadow-lg flex items-center gap-3 max-w-sm"
          >
            <span className="flex-1 text-sm">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="text-white hover:text-red-200 font-bold"
              aria-label="Dismiss"
            >
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
