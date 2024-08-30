import React from "react";
import './CardsView.css';
import TaskCard from "./TaskCard";
import {TaskData} from "../../../interface/TaskData";
interface CardsViewProps {
    tasks: TaskData[];
}
const CardsView = ({ tasks }: CardsViewProps) => {
    return <div className="tasks-view__list">
        {tasks.map((task) => <TaskCard key={task.id} task={task} />)}
    </div>
}

export default CardsView;