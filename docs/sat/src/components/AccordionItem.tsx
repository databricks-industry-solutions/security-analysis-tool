import React, { useState } from 'react';
import { useColorMode } from '@docusaurus/theme-common';

interface AccordionItemProps {
  question: string;
  children: React.ReactNode;
  defaultOpen?: boolean;
}

export default function AccordionItem({ question, children, defaultOpen = false }: AccordionItemProps) {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const { colorMode } = useColorMode();
  const isDark = colorMode === 'dark';

  return (
    <div 
      style={{
        marginBottom: '1rem',
        borderRadius: '8px',
        border: `1px solid ${isDark ? '#444' : '#e0e0e0'}`,
        overflow: 'hidden',
        transition: 'all 0.3s ease',
        backgroundColor: isDark ? '#1e1e1e' : '#ffffff',
      }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: '100%',
          padding: '1rem 1.25rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          border: 'none',
          background: isDark ? '#2a2a2a' : '#f8f9fa',
          cursor: 'pointer',
          fontSize: '1.05rem',
          fontWeight: '600',
          textAlign: 'left',
          transition: 'background-color 0.2s ease',
          color: isDark ? '#ffffff' : '#1c1e21',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = isDark ? '#353535' : '#e9ecef';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = isDark ? '#2a2a2a' : '#f8f9fa';
        }}
      >
        <span style={{ paddingRight: '1rem', lineHeight: '1.5' }}>{question}</span>
        <svg
          width="20"
          height="20"
          viewBox="0 0 20 20"
          fill="none"
          style={{
            transition: 'transform 0.3s ease',
            transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
            flexShrink: 0,
          }}
        >
          <path
            d="M5 7.5L10 12.5L15 7.5"
            stroke={isDark ? '#ffffff' : '#1c1e21'}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <div
        style={{
          maxHeight: isOpen ? '1000px' : '0',
          overflow: 'hidden',
          transition: 'max-height 0.4s ease',
        }}
      >
        <div
          style={{
            padding: '1.25rem',
            lineHeight: '1.7',
            color: isDark ? '#d4d4d4' : '#444',
          }}
        >
          {children}
        </div>
      </div>
    </div>
  );
}

