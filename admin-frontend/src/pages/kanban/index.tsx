import React from 'react';
import { KanbanBoard } from '@/components/kanban';
import './index.css';

const KanbanPage: React.FC = () => {
  return (
    <div className="kanban-page">
      <KanbanBoard />
    </div>
  );
};

export default KanbanPage;
