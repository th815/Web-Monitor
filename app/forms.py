from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, URL, EqualTo

class LoginForm(FlaskForm):
    username = StringField('用户名', validators=[DataRequired()])
    password = PasswordField('密码', validators=[DataRequired()])
    remember_me = BooleanField('记住我')
    submit = SubmitField('登录')
#为 MonitoredSite 创建一个专用的表单
class MonitoredSiteForm(FlaskForm):
    name = StringField('网站名称', validators=[DataRequired(message="请输入网站名称")])
    url = StringField('网站地址 (URL)', validators=[DataRequired(message="请输入URL"), URL(message="请输入有效的URL")])
    is_active = BooleanField('是否启用监控', default=True)

class ChangePasswordForm(FlaskForm):
    """
    Form for users to change their own password.
    """
    current_password = PasswordField('当前密码', validators=[DataRequired()])
    new_password = PasswordField('新密码', validators=[
        DataRequired(),
        EqualTo('确认', message='密码必须匹配。')
    ])
    confirm = PasswordField('确认新密码')
    submit = SubmitField('更新密码')