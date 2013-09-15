<html xmlns:py="http://purl.org/kid/ns#">
<head>
    <link py:strip="1" py:for="css in tg_css">${css.display()}</link>
    <link py:strip="1" py:for="js in tg_js_head">${js.display()}</link>
</head>
<body>
    <div py:replace="form.display(action='testform')"/>
</body>
</html>