# -*- coding: utf-8 -*-
"""
Spyder Editor

This is a temporary script file.
"""

# -*- coding: utf-8 -*-
"""
Created on Sun Aug 09 08:27:30 2015

@author: Administrator
"""

# -*- coding:utf-8 -*- 
"""
交易数据接口 
Created on 2014/07/31
@author: Jimmy Liu
@group : waditu
@contact: jimmysoa@sina.cn
"""
#from __future__ import division



import time
import json
import lxml.html
from lxml import etree
import pandas as pd
import numpy as np
import tushare as ts
from tushare.stock import cons as ct
import re
from pandas.compat import StringIO
from tushare.util import dateu as du
try:
    from urllib.request import urlopen, Request
except ImportError:
    from urllib2 import urlopen, Request

import datetime

import smtplib  
from email.mime.text import MIMEText  


def _parsing_dayprice_json(pageNum=1):
    """
           处理当日行情分页数据，格式为json
     Parameters
     ------
        pageNum:页码
     return
     -------
        DataFrame 当日所有股票交易数据(DataFrame)
    """
    ct._write_console()
    request = Request(ct.SINA_DAY_PRICE_URL%(ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                                 ct.PAGES['jv'], pageNum))
    text = urlopen(request, timeout=10).read()
    if text == 'null':
        return None
    reg = re.compile(r'\,(.*?)\:') 
    text = reg.sub(r',"\1":', text.decode('gbk') if ct.PY3 else text) 
    text = text.replace('"{symbol', '{"symbol')
    text = text.replace('{symbol', '{"symbol"')
    if ct.PY3:
        jstr = json.dumps(text)
    else:
        jstr = json.dumps(text, encoding='GBK')
    js = json.loads(jstr)
    df = pd.DataFrame(pd.read_json(js, dtype={'code':object}),
                      columns=ct.DAY_TRADING_COLUMNS)
    df = df.drop('symbol', axis=1)
    df = df.ix[df.volume > 0]
    return df


def get_tick_data(code=None, date=None, retry_count=3, pause=0.001):
    """
        获取分笔数据
    Parameters
    ------
        code:string
                  股票代码 e.g. 600848
        date:string
                  日期 format：YYYY-MM-DD
        retry_count : int, 默认 3
                  如遇网络等问题重复执行的次数
        pause : int, 默认 0
                 重复请求数据过程中暂停的秒数，防止请求间隔时间太短出现的问题
     return
     -------
        DataFrame 当日所有股票交易数据(DataFrame)
              属性:成交时间、成交价格、价格变动，成交手、成交金额(元)，买卖类型
    """
    if code is None or len(code)!=6 or date is None:
        return None
    symbol = _code_to_symbol(code)
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            re = Request(ct.TICK_PRICE_URL % (ct.P_TYPE['http'], ct.DOMAINS['sf'], ct.PAGES['dl'],
                                date, symbol))
            lines = urlopen(re, timeout=10).read()
            lines = lines.decode('GBK') 
            if len(lines) < 100:
                return None
            df = pd.read_table(StringIO(lines), names=ct.TICK_COLUMNS,
                               skiprows=[0])      
        except Exception as e:
            print(e)
        else:
            return df
    raise IOError(ct.NETWORK_URL_ERROR_MSG)


def get_today_ticks(code=None, retry_count=3, pause=0.001):
    """
        获取当日分笔明细数据
    Parameters
    ------
        code:string
                  股票代码 e.g. 600848
        retry_count : int, 默认 3
                  如遇网络等问题重复执行的次数
        pause : int, 默认 0
                 重复请求数据过程中暂停的秒数，防止请求间隔时间太短出现的问题
     return
     -------
        DataFrame 当日所有股票交易数据(DataFrame)
              属性:成交时间、成交价格、价格变动，成交手、成交金额(元)，买卖类型
    """
    if code is None or len(code)!=6 :
        return None
    symbol = _code_to_symbol(code)
    date = du.today()
    try:
        request = Request(ct.TODAY_TICKS_PAGE_URL % (ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                                                   ct.PAGES['jv'], date,
                                                   symbol))
        data_str = urlopen(request, timeout=10).read()
        data_str = data_str.decode('GBK')
        data_str = data_str[1:-1]
        data_str = eval(data_str, type('Dummy', (dict,), 
                                       dict(__getitem__ = lambda s, n:n))())
        data_str = json.dumps(data_str)
        data_str = json.loads(data_str)
        pages = len(data_str['detailPages'])
        data = pd.DataFrame()
        ct._write_head()
        for pNo in range(1, pages):
            data = data.append(_today_ticks(symbol, date, pNo,
                                            retry_count, pause), ignore_index=True)
    except Exception as er:
        print(str(er))
    return data


def _today_ticks(symbol, tdate, pageNo, retry_count, pause):
    ct._write_console()
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            html = lxml.html.parse(ct.TODAY_TICKS_URL % (ct.P_TYPE['http'],
                                                         ct.DOMAINS['vsf'], ct.PAGES['t_ticks'],
                                                         symbol, tdate, pageNo
                                ))  
            res = html.xpath('//table[@id=\"datatbl\"]/tbody/tr')
            if ct.PY3:
                sarr = [etree.tostring(node).decode('utf-8') for node in res]
            else:
                sarr = [etree.tostring(node) for node in res]
            sarr = ''.join(sarr)
            sarr = '<table>%s</table>'%sarr
            sarr = sarr.replace('--', '0')
            df = pd.read_html(StringIO(sarr), parse_dates=False)[0]
            df.columns = ct.TODAY_TICK_COLUMNS
            df['pchange'] = df['pchange'].map(lambda x : x.replace('%', ''))
        except Exception as e:
            print(e)
        else:
            return df
    raise IOError(ct.NETWORK_URL_ERROR_MSG)
        
    
def get_today_all():
    """
        一次性获取最近一个日交易日所有股票的交易数据
    return
    -------
      DataFrame
           属性：代码，名称，涨跌幅，现价，开盘价，最高价，最低价，最日收盘价，成交量，换手率
    """
    ct._write_head()
    df = _parsing_dayprice_json(1)
    if df is not None:
        for i in range(2, ct.PAGE_NUM[0]):
            newdf = _parsing_dayprice_json(i)
            df = df.append(newdf, ignore_index=True)
    return df


def get_realtime_quotes(symbols=None):
    """
        获取实时交易数据 getting real time quotes data
       用于跟踪交易情况（本次执行的结果-上一次执行的数据）
    Parameters
    ------
        symbols : string, array-like object (list, tuple, Series).
        
    return
    -------
        DataFrame 实时交易数据
              属性:0：name，股票名字
            1：open，今日开盘价
            2：pre_close，昨日收盘价
            3：price，当前价格
            4：high，今日最高价
            5：low，今日最低价
            6：bid，竞买价，即“买一”报价
            7：ask，竞卖价，即“卖一”报价
            8：volumn，成交量 maybe you need do volumn/100
            9：amount，成交金额（元 CNY）
            10：b1_v，委买一（笔数 bid volume）
            11：b1_p，委买一（价格 bid price）
            12：b2_v，“买二”
            13：b2_p，“买二”
            14：b3_v，“买三”
            15：b3_p，“买三”
            16：b4_v，“买四”
            17：b4_p，“买四”
            18：b5_v，“买五”
            19：b5_p，“买五”
            20：a1_v，委卖一（笔数 ask volume）
            21：a1_p，委卖一（价格 ask price）
            ...
            30：date，日期；
            31：time，时间；
    """
    symbols_list = ''
    if type(symbols) is list or type(symbols) is set or type(symbols) is tuple or type(symbols) is pd.Series:
        for code in symbols:
            symbols_list += _code_to_symbol(code) + ','
    else:
        symbols_list = _code_to_symbol(symbols)
        
    symbols_list = symbols_list[:-1] if len(symbols_list) > 8 else symbols_list 
    request = Request(ct.LIVE_DATA_URL%(ct.P_TYPE['http'], ct.DOMAINS['sinahq'],
                                                _random(), symbols_list))
    text = urlopen(request,timeout=10).read()
    text = text.decode('GBK')
    reg = re.compile(r'\="(.*?)\";')
    data = reg.findall(text)
    regSym = re.compile(r'(?:sh|sz)(.*?)\=')
    syms = regSym.findall(text)
    data_list = []
    syms_list = []
    for index, row in enumerate(data):
        if len(row)>1:
            data_list.append([astr for astr in row.split(',')])
            syms_list.append(syms[index])
    if len(syms_list) == 0:
        return None
    df = pd.DataFrame(data_list, columns=ct.LIVE_DATA_COLS)
    df = df.drop('s', axis=1)
    df['code'] = syms_list
    ls = [cls for cls in df.columns if '_v' in cls]
    for txt in ls:
        df[txt] = df[txt].map(lambda x : x[:-2])
    return df


def get_h_data(code, start=None, end=None, autype='qfq',
               index=False, retry_count=3, pause=0.001):
    '''
    获取历史复权数据
    Parameters
    ------
      code:string
                  股票代码 e.g. 600848
      start:string
                  开始日期 format：YYYY-MM-DD 为空时取当前日期
      end:string
                  结束日期 format：YYYY-MM-DD 为空时取去年今日
      autype:string
                  复权类型，qfq-前复权 hfq-后复权 None-不复权，默认为qfq
      retry_count : int, 默认 3
                 如遇网络等问题重复执行的次数 
      pause : int, 默认 0
                重复请求数据过程中暂停的秒数，防止请求间隔时间太短出现的问题
    return
    -------
      DataFrame
          date 交易日期 (index)
          open 开盘价
          high  最高价
          close 收盘价
          low 最低价
          volume 成交量
          amount 成交金额
    '''
    
    start = du.today_last_year() if start is None else start
    end = du.today() if end is None else end
    qs = du.get_quarts(start, end)
    qt = qs[0]
    ct._write_head()
    data = _parse_fq_data(_get_index_url(index, code, qt), index,
                          retry_count, pause)
    if len(qs)>1:
        for d in range(1, len(qs)):
            qt = qs[d]
            ct._write_console()
            df = _parse_fq_data(_get_index_url(index, code, qt), index,
                                retry_count, pause)
            data = data.append(df, ignore_index=True)
    if len(data) == 0 or len(data[(data.date>=start)&(data.date<=end)]) == 0:
        return None
    data = data.drop_duplicates('date')
    if index:
        data = data[(data.date>=start) & (data.date<=end)]
        data = data.set_index('date')
        data = data.sort_index(ascending=False)
        return data
    if autype == 'hfq':
        data = data.drop('factor', axis=1)
        data = data[(data.date>=start) & (data.date<=end)]
        for label in ['open', 'high', 'close', 'low']:
            data[label] = data[label].map(ct.FORMAT)
            data[label] = data[label].astype(float)
        data = data.set_index('date')
        data = data.sort_index(ascending = False)
        return data
    else:
        if autype == 'qfq':
            data = data.drop('factor', axis=1)
            df = _parase_fq_factor(code, start, end)
            df = df.drop_duplicates('date')
            df = df.sort('date', ascending=False)
            frow = df.head(1)
            rt = get_realtime_quotes(code)
            if rt is None:
                return None
            if ((float(rt['high']) == 0) & (float(rt['low']) == 0)):
                preClose = float(rt['pre_close'])
            else:
                if du.is_holiday(du.today()):
                    preClose = float(rt['price'])
                else:
                    if (du.get_hour() > 9) & (du.get_hour() < 18):
                        preClose = float(rt['pre_close'])
                    else:
                        preClose = float(rt['price'])
            
            rate = float(frow['factor']) / preClose
            data = data[(data.date >= start) & (data.date <= end)]
            for label in ['open', 'high', 'low', 'close']:
                data[label] = data[label] / rate
                data[label] = data[label].map(ct.FORMAT)
                data[label] = data[label].astype(float)
            data = data.set_index('date')
            data = data.sort_index(ascending = False)
            return data
        else:
            for label in ['open', 'high', 'close', 'low']:
                data[label] = data[label] / data['factor']
            data = data.drop('factor', axis=1)
            data = data[(data.date>=start) & (data.date<=end)]
            for label in ['open', 'high', 'close', 'low']:
                data[label] = data[label].map(ct.FORMAT)
            data = data.set_index('date')
            data = data.sort_index(ascending=False)
            data = data.astype(float)
            return data


def _parase_fq_factor(code, start, end):
    symbol = _code_to_symbol(code)
    request = Request(ct.HIST_FQ_FACTOR_URL%(ct.P_TYPE['http'],
                                             ct.DOMAINS['vsf'], symbol))
    text = urlopen(request, timeout=10).read()
    text = text[1:len(text)-1]
    text = text.decode('utf-8') if ct.PY3 else text
    text = text.replace('{_', '{"')
    text = text.replace('total', '"total"')
    text = text.replace('data', '"data"')
    text = text.replace(':"', '":"')
    text = text.replace('",_', '","')
    text = text.replace('_', '-')
    text = json.loads(text)
    df = pd.DataFrame({'date':list(text['data'].keys()), 'factor':list(text['data'].values())})
    df['date'] = df['date'].map(_fun_except) # for null case
    if df['date'].dtypes == np.object:
        df['date'] = df['date'].astype(np.datetime64)
    df = df.drop_duplicates('date')
    df['factor'] = df['factor'].astype(float)
    return df


def _fun_except(x):
    if len(x) > 10:
        return x[-10:]
    else:
        return x


def _parse_fq_data(url, index, retry_count, pause):
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            request = Request(url)
            text = urlopen(request, timeout=10).read()
            text = text.decode('GBK')
            html = lxml.html.parse(StringIO(text))
            res = html.xpath('//table[@id=\"FundHoldSharesTable\"]')
            if ct.PY3:
                sarr = [etree.tostring(node).decode('utf-8') for node in res]
            else:
                sarr = [etree.tostring(node) for node in res]
            sarr = ''.join(sarr)
            df = pd.read_html(sarr, skiprows = [0, 1])[0]
            if len(df) == 0:
                return pd.DataFrame()
            if index:
                df.columns = ct.HIST_FQ_COLS[0:7]
            else:
                df.columns = ct.HIST_FQ_COLS
            if df['date'].dtypes == np.object:
                df['date'] = df['date'].astype(np.datetime64)
            df = df.drop_duplicates('date')
        except Exception as e:
            print(e)
        else:
            return df
    raise IOError(ct.NETWORK_URL_ERROR_MSG)


def get_index():
    """
    获取大盘指数行情
    return
    -------
      DataFrame
          code:指数代码
          name:指数名称
          change:涨跌幅
          open:开盘价
          preclose:昨日收盘价
          close:收盘价
          high:最高价
          low:最低价
          volume:成交量(手)
          amount:成交金额（亿元）
    """
    request = Request(ct.INDEX_HQ_URL%(ct.P_TYPE['http'],
                                             ct.DOMAINS['sinahq']))
    text = urlopen(request, timeout=10).read()
    text = text.decode('GBK')
    text = text.replace('var hq_str_sh', '').replace('var hq_str_sz', '')
    text = text.replace('";', '').replace('"', '').replace('=', ',')
    text = '%s%s'%(ct.INDEX_HEADER, text)
    df = pd.read_csv(StringIO(text), sep=',', thousands=',')
    df['change'] = (df['close'] / df['preclose'] - 1 ) * 100
    df['amount'] = df['amount'] / 100000000
    df['change'] = df['change'].map(ct.FORMAT)
    df['amount'] = df['amount'].map(ct.FORMAT)
    df = df[ct.INDEX_COLS]
    df['code'] = df['code'].map(lambda x:str(x).zfill(6))
    df['change'] = df['change'].astype(float)
    df['amount'] = df['amount'].astype(float)
    return df
 

def _get_index_url(index, code, qt):
    if index:
        url = ct.HIST_INDEX_URL%(ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                              code, qt[0], qt[1])
    else:
        url = ct.HIST_FQ_URL%(ct.P_TYPE['http'], ct.DOMAINS['vsf'],
                              code, qt[0], qt[1])
    return url
    
    
def _random(n=13):
    from random import randint
    start = 10**(n-1)
    end = (10**n)-1
    return str(randint(start, end))

def get_hist_data(code=None, start=None, end=None,
                  ktype='D', retry_count=3,
                  pause=0.001):
    """
        获取个股历史交易记录
    Parameters
    ------
      code:string
                  股票代码 e.g. 600848
      start:string
                  开始日期 format：YYYY-MM-DD 为空时取到API所提供的最早日期数据
      end:string
                  结束日期 format：YYYY-MM-DD 为空时取到最近一个交易日数据
      ktype：string
                  数据类型，D=日k线 W=周 M=月 5=5分钟 15=15分钟 30=30分钟 60=60分钟，默认为D
      retry_count : int, 默认 3
                 如遇网络等问题重复执行的次数 
      pause : int, 默认 0
                重复请求数据过程中暂停的秒数，防止请求间隔时间太短出现的问题
    return
    -------
      DataFrame
          属性:日期 ，开盘价， 最高价， 收盘价， 最低价， 成交量， 价格变动 ，涨跌幅，5日均价，10日均价，20日均价，5日均量，10日均量，20日均量，换手率
    """
    symbol = _code_to_symbol(code)
    url = ''
    if ktype.upper() in ct.K_LABELS:
        url = ct.DAY_PRICE_URL%(ct.P_TYPE['http'], ct.DOMAINS['ifeng'],
                                ct.K_TYPE[ktype.upper()], symbol)
    elif ktype in ct.K_MIN_LABELS:
        url = ct.DAY_PRICE_MIN_URL%(ct.P_TYPE['http'], ct.DOMAINS['ifeng'],
                                    symbol, ktype)
    else:
        raise TypeError('ktype input error.')
    
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            request = Request(url)
            lines = urlopen(request, timeout = 10).read()
            if len(lines) < 20: #no data
                return None
        except Exception as e:
            print(e)
        else:
            js = json.loads(lines.decode('utf-8') if ct.PY3 else lines)
            cols = []
            if (code in ct.INDEX_LABELS) & (ktype.upper() in ct.K_LABELS):
                cols = ct.INX_DAY_PRICE_COLUMNS
            else:
                cols = ct.DAY_PRICE_COLUMNS
            if len(js['record'][0]) == 19:
                cols = ct.INX_DAY_PRICE_COLUMNS
            df = pd.DataFrame(js['record'], columns=cols)
            if ktype.upper() in ['D', 'W', 'M']:
                df = df.applymap(lambda x: x.replace(u',', u''))
            for col in cols[1:]:
                df[col] = df[col].astype(float)
            if start is not None:
                df = df[df.date >= start]
            if end is not None:
                df = df[df.date <= end]
            if (code in ct.INDEX_LABELS) & (ktype in ct.K_MIN_LABELS):
                df = df.drop('turnover', axis=1)
            df = df.set_index('date')
            return df
    raise IOError(ct.NETWORK_URL_ERROR_MSG)

def _code_to_symbol(code):
    """
        生成symbol代码标志
    """
    if code in ct.INDEX_LABELS:
        return ct.INDEX_LIST[code]
    else:
        if len(code) != 6 :
            return ''
        else:
            return 'sh%s'%code if code[:1] in ['5', '6'] else 'sz%s'%code

def floatrange(start,stop,value):
    ''' Computes a range of floating value.
        
        Input:
            start (float)  : Start value.
            end   (float)  : End value
            steps (integer): Number of values
        
        Output:
            A list of floats
        
        Example:
            >>> print floatrange(0.25, 1.3, 5)
            [0.25, 0.51249999999999996, 0.77500000000000002, 1.0375000000000001, 1.3]
    '''
    steps = int((stop - start) / value)
    return [start+float(i)*(stop-start)/(float(steps)-1) for i in range(steps)]
            
def get_hist_data_evers(code=None, start=None, end=None,
                  ktype='D', retry_count=3,
                  pause=0.001):
    """
        获取个股历史交易记录
    Parameters
    ------
      code:string
                  股票代码 e.g. 600848
      start:string
                  开始日期 format：YYYY-MM-DD 为空时取到API所提供的最早日期数据
      end:string
                  结束日期 format：YYYY-MM-DD 为空时取到最近一个交易日数据
      ktype：string
                  数据类型，D=日k线 W=周 M=月 5=5分钟 15=15分钟 30=30分钟 60=60分钟，默认为D
      retry_count : int, 默认 3
                 如遇网络等问题重复执行的次数 
      pause : int, 默认 0
                重复请求数据过程中暂停的秒数，防止请求间隔时间太短出现的问题
    return
    -------
      DataFrame
          属性:日期 ，开盘价， 最高价， 收盘价， 最低价， 成交量， 价格变动 ，涨跌幅，5日均价，10日均价，20日均价，5日均量，10日均量，20日均量，换手率
    """
    symbol = _code_to_symbol(code)
    url = ''
    if ktype.upper() in ct.K_LABELS:
        url = ct.DAY_PRICE_URL%(ct.P_TYPE['http'], ct.DOMAINS['ifeng'],
                                ct.K_TYPE[ktype.upper()], symbol)
    elif ktype in ct.K_MIN_LABELS:
        url = ct.DAY_PRICE_MIN_URL%(ct.P_TYPE['http'], ct.DOMAINS['ifeng'],
                                    symbol, ktype)
    else:
        raise TypeError('ktype input error.')
    
    for _ in range(retry_count):
        time.sleep(pause)
        try:
            request = Request(url)
            lines = urlopen(request, timeout = 10).read()
            if len(lines) < 15: #no data
                return None
        except Exception as e:
            print(e)
        else:
            js = json.loads(lines.decode('utf-8') if ct.PY3 else lines)
            cols = []
            if (code in ct.INDEX_LABELS) & (ktype.upper() in ct.K_LABELS):
                cols = ct.INX_DAY_PRICE_COLUMNS
            else:
                cols = ct.DAY_PRICE_COLUMNS
            if len(js['record'][0]) == 14:
                cols = ct.INX_DAY_PRICE_COLUMNS
            df = pd.DataFrame(js['record'], columns=cols)
            if ktype.upper() in ['D', 'W', 'M']:
                df = df.applymap(lambda x: x.replace(u',', u''))
            for col in cols[1:]:
                df[col] = df[col].astype(float)
            
            now = datetime.datetime.now()
            delta = datetime.timedelta(days=60)
            n_days = now - delta
            start = n_days.strftime('%Y-%m-%d')  
            if start is not None:
                df = df[df.date >= start]
            if end is not None:
                df = df[df.date <= end]
            if (code in ct.INDEX_LABELS) & (ktype in ct.K_MIN_LABELS):
                df = df.drop('turnover', axis=1)
                
            df = df.set_index('date')
            return df
    raise IOError(ct.NETWORK_URL_ERROR_MSG)
    
def calc_X_days_average(df, days):
    X_days_high = 0
    X_days_max = 0
    X_days_low = 0
    X_days_min = 1000
    for i in range(0, len(df)):
        X_days_high = X_days_high + df.irow(i).high
        if (df.irow(i).high > X_days_max):
            X_days_max = df.irow(i).high
#        print df.irow(i).high
        X_days_low = X_days_low + df.irow(i).low
        if (df.irow(i).low < X_days_min):
            X_days_min = df.irow(i).low        
#        print df.irow(i).low
        if (i == days - 1):
            break
#        print " "
    return round(float(X_days_high/days),2),round(float(X_days_low/days),2),X_days_max,X_days_min

def calc_sell_num(price_buy, price_sell,debug,df):       
    bought = False
    sell_num = 0
    date_info=""
    for i in range(0, len(df)):
        if (not bought and df.irow(i).low < price_buy):
            date_info=date_info+df.irow(i).name+"->"
            bought = True
        elif (bought and df.irow(i).high > price_sell):
            date_info=date_info+df.irow(i).name+"\n"
            bought = False
            sell_num = sell_num +1
    if (debug):
        print date_info
    return sell_num
   #     print "Totally sell for %d times , value is %f"%(sell_num,sell_num*(price_sell-price_buy))


#print calc_sell_num('000938',65,70)

"""
#zhong xing
for i in floatrange(15, 28, 0.1):
    sell=i+0.7
    nums=calc_sell_num('000063',i,sell,False)
    print "buy=%f, sell=%f, nums=%d, value=%f"%(i,sell,nums,nums*(sell-i))
    #print "\n"
"""

def send_email(subject, content):
    sender = '873221@qq.com'  
    receiver = '873221@qq.com'  
    #subject = subject  
    smtpserver = 'smtp.qq.com'  
    username = '873221@qq.com'  
    password = 'evers!55555'  
      
    msg = MIMEText('<html><h1>'+content+'</h1></html>','html','utf-8') 
    
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = receiver
    msg['Cc'] = '1070608222@qq.com'
    
    
      
    smtp = smtplib.SMTP()  
    smtp.connect('smtp.qq.com')  
    smtp.login(username, password)  
    smtp.sendmail(sender, receiver, msg.as_string())  
    smtp.quit() 

#lian tong


def my_calc(code):
    content=""
    aa=get_realtime_quotes(code)
    code_name = aa.irow(0)[0]
    current_price=aa.irow(0).price
    print current_price
    
    now = datetime.datetime.now()
    delta = datetime.timedelta(days=60)
    n_days = now - delta
    start = n_days.strftime('%Y-%m-%d')
                
    df=get_hist_data(code,start)
    df=df.sort(ascending=False)
    lowest=df.min().low
    highest=df.max().high
    
    dd = df[['high','low','close','ma5','ma10']]
    dd = dd.to_html()
    step=(lowest/6)*0.05
    step=round(step,2)
    if (step < 0.05):
        step=0.05
    df = get_hist_data_evers(code)
    df=df.sort(ascending=False)
    max_nums = 0
    max_info = ""
    T_days_high,T_days_low,T_days_max,T_days_min = calc_X_days_average(df, 10)
    F_days_high,F_days_low,F_days_max,F_days_min = calc_X_days_average(df, 5)
#    print X_days_high
#    print X_days_low
    Current_info = "<font size='3'>Current Price: %s</font>"%(current_price)
    T_days_info = "<br><font size='3'> 10 days average: %.2f, %.2f --> %.2f, %.2f</font>"%(T_days_min,T_days_low,T_days_high,T_days_max)
    F_days_info = "<br><font size='3'> 5 days average: %.2f, %.2f --> %.2f, %.2f</font>"%(F_days_min,F_days_low,F_days_high,F_days_max)
    Hist_info = "<br><font size='3'> History Price: %.2f --> %.2f</font><br><br>"%(lowest,highest)
    for i in floatrange(lowest, highest, step):
        buy = round(i,2)
        sell = round(buy+buy*0.03,2)
        nums=calc_sell_num(i,sell,False,df)
        if (nums > max_nums):
            max_nums = nums
            max_info = "<br><font size='3'>buy=%.2f, sell=%.2f, nums=%d</font>"%(buy,sell,nums)
        elif (nums == max_nums):
            max_info = max_info + "<br><font size='3'>buy=%.2f, sell=%.2f, nums=%d</font>"%(buy,sell,nums)
        print "buy=%.2f, sell=%.2f, nums=%d, value=%.2f"%(buy,sell,nums,nums*(sell-i))
        if (nums):
            content=content+ "<br><font size='3'>buy=%.2f, sell=%.2f, nums=%d</font>"%(buy,sell,nums)
        #print "\n"   
    today = now.strftime('%Y-%m-%d')
    send_email(code+" "+code_name + " " + today, Current_info + max_info + T_days_info + F_days_info + Hist_info + dd + content)


def my_sell_notify(code):
    content=""
    aa=get_realtime_quotes(code)
    code_name = aa.irow(0)[0]
    current_price=float(aa.irow(0).price)
#    print current_price
    
    now = datetime.datetime.now()
    delta = datetime.timedelta(days=60)
    n_days = now - delta
    start = n_days.strftime('%Y-%m-%d')
                
    df=get_hist_data(code,start)
    df=df.sort(ascending=False)
    lowest=df.min().low
    highest=df.max().high
    
    dd = df[['high','low','close','ma5','ma10']]
    dd = dd.to_html()
    step=(lowest/6)*0.05
    step=round(step,2)
    if (step < 0.05):
        step=0.05
    df = get_hist_data_evers(code)
    df=df.sort(ascending=False)
    max_nums = 0
    max_info = ""
    T_days_high,T_days_low,T_days_max,T_days_min = calc_X_days_average(df, 10)
    F_days_high,F_days_low,F_days_max,F_days_min = calc_X_days_average(df, 5)
#    print X_days_high
#    print X_days_low
    Current_info = "<font size='3'>Current Price: %s</font>"%(current_price)
    T_days_info = "<br><font size='3'> 10 days average: %.2f, %.2f --> %.2f, %.2f</font>"%(T_days_min,T_days_low,T_days_high,T_days_max)
    F_days_info = "<br><font size='3'> 5 days average: %.2f, %.2f --> %.2f, %.2f</font>"%(F_days_min,F_days_low,F_days_high,F_days_max)
    Hist_info = "<br><font size='3'> History Price: %.2f --> %.2f</font><br><br>"%(lowest,highest)

    today = now.strftime('%Y-%m-%d')
    
    if (current_price > T_days_high) or (current_price > F_days_high):
        content += code_name + "is ready to sell, current price: %.2f 5 days high: %.2f 10 days high: %.2f"%(current_price,F_days_high,T_days_high)
    return content

#codes=['600028']
codes=['600030','600895','600648','600663','600639','601566','002769','000002','600118','600050','600036']
codes.extend(['002242','600100','601766','000063','000938']) #my stock

mycodes = ['002242','600100','601766','000063','000938']





df = get_today_all()

kk = df.sort(columns='turnoverratio', ascending=False)
kk = kk.head(50)

mm = df.sort(columns='volume', ascending=False)
mm = mm.head(50)

dd = kk[['code','name','changepercent','volume','turnoverratio']]

ll = mm[['code','name','changepercent','volume','turnoverratio']]

print "\n"
    
print dd
print "\n"

print ll

