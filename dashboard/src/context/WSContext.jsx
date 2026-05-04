import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { createWebSocket } from '../api';

const WSContext = createContext(null);

export function WSProvider({ children }) {
  const [status, setStatus] = useState('connecting'); // connecting | connected | disconnected
  const [lastEvent, setLastEvent] = useState(null);
  const [streams, setStreams] = useState([]);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  const connect = () => {
    setStatus('connecting');
    wsRef.current = createWebSocket(
      (msg) => {
        if (msg.type === 'event') setLastEvent(msg.data);
        if (msg.type === 'init' || msg.type === 'heartbeat') {
          if (msg.data?.streams) setStreams(msg.data.streams);
        }
      },
      () => {
        setStatus('connected');
        clearTimeout(reconnectRef.current);
      },
      () => {
        setStatus('disconnected');
        // Auto-reconnect after 3s
        reconnectRef.current = setTimeout(connect, 3000);
      }
    );
  };

  useEffect(() => {
    connect();
    return () => {
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, []);

  return (
    <WSContext.Provider value={{ status, lastEvent, streams, ws: wsRef.current }}>
      {children}
    </WSContext.Provider>
  );
}

export const useWS = () => useContext(WSContext);
