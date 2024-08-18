import React from "react";
import {TaskData} from "../../../interface/TaskData";

interface TaskCardProps {
    task: TaskData;
}
const TaskCard = ({ task }: TaskCardProps) => {
    return <div className="tasks-card_tags">
        {task.imageSrc && <img className="tasks-card_tags__image" src={task.imageSrc} alt={task.title}/>}
        <span>{task.title}</span>
    </div>
}

export default TaskCard;