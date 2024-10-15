import './Navbar.css';
import Logo from "../Logo";
import UserMenu from "./UserMenu";

const Navbar = () => {
    return <nav id="navbar">
        <div className="navbar__logo">
            <Logo/>
        </div>
        <div className="navbar__controls">
            <UserMenu/>
        </div>
    </nav>
}

export default Navbar;