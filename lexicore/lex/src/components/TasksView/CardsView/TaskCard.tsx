import React from "react";

interface TaskCardProps {
    task: any;
}
const TaskCard = ({ task }: TaskCardProps) => {
    return <div key={task.title} className="tasks-card">
        {task.imageSrc && <img className="tasks-card__image" src={task.imageSrc} alt={task.title}/>}
        <span>{task.title}</span>
    </div>
}

export default TaskCard;