
from kivymd.app import MDApp
from kivy.uix.screenmanager import ScreenManager, Screen
from kivymd.uix.button import MDRectangleFlatButton
from kivymd.uix.boxlayout import MDBoxLayout


class MainScreen(Screen):
    def __init__(self, **kwargs):
        super(MainScreen, self).__init__(**kwargs)
        layout = MDBoxLayout(orientation='vertical', padding=10, spacing=10)

        self.module_buttons = [
            ("Game Studio", "game_studio"),
            ("Robotics Simulator", "robotics_simulator"),
            ("AI Assistant", "ai_assistant"),
            ("Electronics Builder", "electronics_builder"),
            ("Coding Environment", "coding_environment"),
            ("Learning Hub", "learning_hub"),
            ("Creative Engine", "creative_engine"),
            ("Dashboard", "dashboard")
        ]

        for name, screen_name in self.module_buttons:
            btn = MDRectangleFlatButton(text=name, size_hint_x=None, width=200)
            btn.bind(on_press=lambda x, s=screen_name: self.switch_screen(s))
            layout.add_widget(btn)

        self.add_widget(layout)

    def switch_screen(self, screen_name):
        self.manager.current = screen_name


class MechaLoopApp(MDApp):
    def build(self):
        sm = ScreenManager()
        sm.add_widget(MainScreen(name='main'))

        # Create dummy screens for each module
        for _, screen_name in sm.get_screen('main').module_buttons:
            sm.add_widget(Screen(name=screen_name))

        return sm

if __name__ == '__main__':
    MechaLoopApp().run()
