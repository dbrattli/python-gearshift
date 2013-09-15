<html xmlns:py="http://purl.org/kid/ns#">
<body>
    <div py:replace="spy"/>
    data="<div py:for="x in data" py:replace="x"/>"
</body>
</html>