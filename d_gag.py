from pickle import FALSE
from select import select
from telegram import Update
from telegram.ext import CallbackContext
import sys
import redis
import json
c_GAGTYPES = {
    '胡萝卜口塞': [1, 0],  # 名稱:[一次加多少,多少絨度可以被使用]
    '口塞球': [3, 10],
    '充气口塞球': [5, 100],
    '深喉口塞': [7, 500],
    '金属开口器': [9, 1000],
    '炮机口塞': [11, 1500],
    '永久口塞': [65536, 65536],
}
# redis 記錄格式： [[剩餘次數,用具名稱],[參與人員陣列]]


def canUse(point: int) -> list[str]:
    """根據當前絨度列出支援使用的道具"""
    gagKeys = list(c_GAGTYPES.keys())
    canUseNames: list[str] = []
    for gagName in gagKeys:
        gagInfo = c_GAGTYPES[gagName]
        needPoint = gagInfo[1]
        if point >= needPoint:
            canUseNames.append(gagName)
    return canUseNames


def rpoint(redisConnect: redis.Redis, user: str, change: int) -> int:
    """查詢或修改絨度"""
    rediskey: str = 'rpt_' + str(user)
    point = 0
    rpointInfo = redisConnect.get(rediskey)
    if rpointInfo != None and len(rpointInfo) > 0:
        rpointInfo = rpointInfo.decode()
        print('get',rpointInfo)
        point = int(rpointInfo)
    if change != 0:
        point += change
        if point < 0:
            point = 0
        print('set',str(point))
        redisConnect.set(rediskey, str(point))
    return point


def add(update: Update, context: CallbackContext, redisPool0: redis.ConnectionPool, c_CHAR: list[list[str]]):
    """為他人佩戴口球"""
    argsLen = len(context.args)
    if argsLen == 0:
        return
    gagTypesKeys = list(c_GAGTYPES.keys())
    gagName: str = gagTypesKeys[0]
    if argsLen == 2:
        if gagName in gagTypesKeys:
            gagName = context.args[1]
    toUser: str = context.args[0]
    if toUser == 'help':
        return
    if toUser[0] != '@':
        return
    fromUser: str = '@'+update.message.from_user.username
    chatID: int = update.message.chat.id
    redisConnect = redis.Redis(connection_pool=redisPool0)
    rediskey: str = 'gag_' + str(chatID) + '_' + str(toUser)
    gagInfo = redisConnect.get(rediskey)
    alert: str = ''
    if gagInfo != None and len(gagInfo) > 0:
        gagInfo = gagInfo.decode()
        if gagInfo == '0':
            redisConnect.close()
            alert = toUser+' 刚刚挣脱口塞！请给对方 1 分钟的休息时间！'
            print(alert)
            context.bot.send_message(
                chat_id=update.effective_chat.id, text=alert)
            return
        infoArr = json.loads(gagInfo)
        infoArrInf = infoArr[0]
        names: list[str] = infoArr[1]
        gagTotal: int = infoArrInf[0]
        gagName = infoArrInf[1]
        isRepeat = False
        for name in names:
            if name == fromUser:
                isRepeat = True
                break
        if isRepeat:
            alert = '抱歉， '+fromUser+' 。你已经为 '+toUser + \
                ' 佩戴过 '+gagName+' 了，请在 '+toUser+' 挣脱后再试。'
        else:
            gagTotal += 5
            infoArrInf[0] = gagTotal
            infoArr[0] = infoArrInf
            names.append(fromUser)
            infoArr[1] = names
            gagInfo = json.dumps(infoArr)
            redisConnect.set(rediskey, gagInfo, ex=600)
            alert = fromUser+' 加固了 '+toUser+' 的 '+gagName+' ！'
        alert += '\n'+toUser+' 目前佩戴着被 ' + \
            (' 、 '.join(names))+' 安装或加固的 '+gagName + \
            ' ，还需要挣扎 '+str(gagTotal)+' 次才能把它挣脱！'
    else:
        selectGagInfo = c_GAGTYPES[gagName]
        selectGagAdd: int = selectGagInfo[0]
        selectGagNeed: int = selectGagInfo[1]
        point: int = rpoint(redisConnect, toUser, 0)
        if point < selectGagNeed:
            redisConnect.close()
            canUseNames: list[str] = canUse(point)
            alert = fromUser+' 抱歉，由于 '+toUser+' 的绒度不够，你不能给 '+toUser+' 佩戴 ' + \
                gagName+' ，需要等待对方绒度达到 '+str(selectGagNeed)+' 才行。\n'+toUser+' 当前绒度为 ' + \
                str(point)+' ，目前可以使用的口塞有 '+(' 、 '.join(canUseNames)) + \
                ' 。\n要查询自己的绒度，使用 `/rbqpoint` ；要查询每个绒度对应可用口塞，使用 `/gag help` 。'
            print(alert)
            context.bot.send_message(
                chat_id=update.effective_chat.id, text=alert)
            return
        gagInfo = json.dumps([[selectGagAdd, gagName], [fromUser]])
        redisConnect.set(rediskey, gagInfo,ex=600)
        alert = fromUser+' 为 '+toUser+' 戴上了 '+gagName+' ！\n'+toUser+' 必须挣扎 '+str(selectGagAdd)+' 次才能挣脱它！\n其他人可以继续用同样指令加固 '+toUser+' 的 '+gagName+' （但同一个人只能在对方挣脱后才能再次为对方佩戴或加固）。\n' + \
            toUser+' 请注意：现在你只能发送包含如下文字的消息（单字或组合成词）「' + \
            ('、'.join(c_CHAR[0]))+'」，可以使用的标点限制为「' + \
            ('、'.join(c_CHAR[1]))+'」，每发送一条消息算作挣扎一次，包含其他字符的消息不能发送！\n如果 10 分钟没有任何加固或挣扎操作，将会自动解除。'
    redisConnect.close()
    if fromUser == toUser:
        alert += '\n咦？！居然自己给自己戴？真是个可爱的绒布球呢！'
    print(alert)
    context.bot.send_message(chat_id=update.effective_chat.id, text=alert)


def chk(update: Update, context: CallbackContext, redisPool0: redis.ConnectionPool, c_CHAR: list[list[str]]) -> bool:
    """檢查加固值是否應該變化"""
    text: str = update.message.text
    fromUser: str = '@'+update.message.from_user.username
    chatID: int = update.message.chat.id
    redisConnect = redis.Redis(connection_pool=redisPool0)
    rediskey: str = 'gag_' + str(chatID) + '_' + str(fromUser)
    gagInfo = redisConnect.get(rediskey)
    if gagInfo != None and len(gagInfo) > 0:
        gagInfo = gagInfo.decode()
        if gagInfo == '0':
            redisConnect.close()
            return False
        infoArr = json.loads(gagInfo)
        infoArrInf = infoArr[0]
        gagTotal: int = int(infoArrInf[0])
        gagName: str = infoArrInf[1]
        names = infoArr[1]
        gagTotal -= 1
        if gagTotal <= 0:
            redisConnect.set(rediskey, '0', ex=60)
            point = rpoint(redisConnect, fromUser, 1)
            print(fromUser+' -1 = '+str(gagTotal))
            alert: str = fromUser + ' 挣脱了被 ' + \
                (' 、 '.join(names))+' 佩戴或加固的 '+gagName + \
                ' ！现在可以自由说话了！\n接下来 1 分钟为强制休息时间，期间不能再被佩戴任何口塞哦。\n现在 '+fromUser+' 的绒度升到了 '+str(point)+' ！'
            print(alert)
            context.bot.send_message(
                chat_id=update.effective_chat.id, text=alert)
        else:
            isOK = True
            charAll = c_CHAR[0] + c_CHAR[1]
            for msgChar in text:
                isInChar = False
                for dbChar in (charAll):
                    if msgChar == dbChar:
                        isInChar = True
                        break
                if isInChar == False:
                    isOK = False
                    break
            if isOK:
                infoArrInf[0] = gagTotal
                infoArr[0] = infoArrInf
                gagInfo = json.dumps(infoArr)
                redisConnect.set(rediskey, gagInfo, ex=600)
                gagTotalStr: str = str(gagTotal)
                rpoint(redisConnect, fromUser, 1)
                print(fromUser+' -1 = '+gagTotalStr)
                singleNum: str = gagTotalStr[-1]
                if singleNum == '5' or singleNum == '0':
                    alert = fromUser+' 加油！还有 '+gagTotalStr+' 次！'
                    print(alert)
                    context.bot.send_message(
                        chat_id=update.effective_chat.id, text=alert)
            else:
                context.bot.delete_message(
                    chat_id=update.message.chat_id, message_id=update.message.message_id)
                print(fromUser+' -0 = '+str(gagTotal))
        redisConnect.close()
        return True
    redisConnect.close()
    return False