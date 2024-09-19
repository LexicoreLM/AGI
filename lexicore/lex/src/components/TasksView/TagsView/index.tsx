import React, {useMemo} from "react";
import './TagsView.css';
import TaskCard from "./TaskCard";
import {TaskData} from "../../../interface/TaskData";

interface CardsViewProps {
    tasks: TaskData[];
}

const TagsView = ({tasks}: CardsViewProps) => {
    const tasksMapByTags: Record<string, TaskData[]> = useMemo(() => {
        return tasks.reduce((acc: Record<string, TaskData[]>, task) => {
            task.tags.forEach((tag) => {
                acc[tag] = (acc[tag] ?? []).concat(task);
            });

            return acc;
        }, {});
    }, [tasks]);

    return <div className="tasks-view__cards">
        {Object.entries(tasksMapByTags).map(([tag, tasks], ind) => {
            return <div key={ind} className="task-tag__container">
                <p>{tag}</p>
                <div className="task-tag__cards">
                    {tasks.map((task) => <TaskCard key={task.id} task={task}/>)}
                </div>
            </div>
        })}
    </div>
}

export default TagsView;