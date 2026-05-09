import {
    _decorator,
    Component,
} from "cc";

const { ccclass } = _decorator;

/**
 * 游戏管理器（全局单例）
 */
@ccclass("GameManager")
export class GameManager extends Component {
    public static instance: GameManager = null;

    protected onLoad(): void {
        if (GameManager.instance === null) {
            GameManager.instance = this;
        } else {
            this.node.destroy();
        }
    }

    protected onDestroy(): void {
        if (GameManager.instance === this) {
            GameManager.instance = null;
        }
    }
}
